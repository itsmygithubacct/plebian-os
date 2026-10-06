"""An update killed mid-transaction is detected, and --recover-interrupted undoes it."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPDATE_PATH = ROOT / "provision" / "plebian-os-update.sh"
ROOT_TXN = "/var/lib/plebian-os/update-rollback.Fixture1"

# Stubs replace only the privileged or slow primitives; the detection, the
# refusal and the recovery decisions under test are the updater's own code.
STUBS = r'''
acquire_kilix_transaction_lock() { echo lock >>"$LOG"; }
release_kilix_transaction_lock() { echo unlock >>"$LOG"; }
validate_root_transaction_dir() { [[ "$1" == /var/lib/plebian-os/update-rollback.* ]]; }
remove_root_stack_snapshot() { echo "remove-root $1" >>"$LOG"; }
rollback_stack_transaction() {
    echo "rollback dir=$_STACK_TXN_DIR root=$_STACK_ROOT_TXN_DIR native=$NATIVE_TRANSACTION_STARTED:$NATIVE_TRANSACTION_TOKEN" >>"$LOG"
    return "${ROLLBACK_RC:-0}"
}
finish_native_runtime_transaction() { echo "finish $NATIVE_TRANSACTION_TOKEN" >>"$LOG"; }
'''


class InterruptedUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="interrupted-update-"))
        self.addCleanup(subprocess.run, ["rm", "-rf", str(self.tmp)])
        self.state = self.tmp / "state"
        self.state.mkdir(mode=0o700)
        self.log = self.tmp / "log"
        self.log.write_text("")

    def run_lib(self, body, **extra):
        env = {k: v for k, v in os.environ.items() if not k.startswith("PLEBIAN_OS_")}
        env.update({"HOME": str(self.tmp / "home"), "LOG": str(self.log),
                    # never this machine's own installation record
                    "PLEBIAN_OS_INSTALLED_VERSIONS": str(self.tmp / "no-versions.env"), **extra})
        script = (
            "set -euo pipefail\n"
            "export PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY=1\n"
            f"PLEB_STATE_HOME={str(self.state)!r}\n"
            f"source {str(UPDATE_PATH)!r}\n"
            f"PLEB_STATE_HOME={str(self.state)!r}\n"
            + STUBS + body)
        return subprocess.run(["bash", "-c", script], env=env, text=True,
                              capture_output=True, check=False, timeout=60)

    DEAD = "pid=999999\nstart=1\nboot=gone\n"

    def orphan(self, name="stack-rollback.Abc123", owner=DEAD, **markers):
        d = self.state / name
        d.mkdir(mode=0o700)
        if owner is not None:                    # owner=None: left by an earlier updater
            (d / "owner").write_text(owner)
        for key, value in markers.items():
            (d / key.replace("_", "-")).write_text(value)
        return d

    def boot_id(self):
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()

    def test_only_transactions_whose_owner_is_gone_count_as_interrupted(self):
        live = subprocess.Popen(["sleep", "60"])
        self.addCleanup(live.wait)
        self.addCleanup(live.kill)
        start = Path(f"/proc/{live.pid}/stat").read_text().rsplit(") ", 1)[1].split()[19]
        alive = self.orphan("stack-rollback.Live01",
                            owner=f"pid={live.pid}\nstart={start}\nboot={self.boot_id()}\n")
        dead = self.orphan("stack-rollback.Dead01",
                           owner=f"pid=999999\nstart=1\nboot={self.boot_id()}\n")
        rebooted = self.orphan("stack-rollback.Boot01",
                               owner=f"pid={live.pid}\nstart={start}\nboot=another-boot\n")
        reused = self.orphan("stack-rollback.Reuse1",   # same PID, a different process
                             owner=f"pid={live.pid}\nstart={int(start) + 1}\nboot={self.boot_id()}\n")
        legacy = self.orphan("stack-rollback.Legacy", owner=None)
        self.orphan("stack-rollback.Failed", failure_reason="exit-status: 1\n")
        self.orphan("stack-rollback.Native", native_finish_pending="token\n")
        result = self.run_lib("interrupted_stack_transactions\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        listed = set(result.stdout.split())
        # An earlier updater's leftover records no owner and never counts.
        self.assertEqual(listed, {str(dead), str(rebooted), str(reused)})
        self.assertNotIn(str(legacy), listed)
        self.assertNotIn(str(alive), listed)

    def test_own_owner_record_reads_as_alive(self):
        d = self.orphan("stack-rollback.Self01")
        result = self.run_lib(
            f"record_stack_transaction_owner {str(d)!r}\n"
            f"stack_transaction_owner_alive {str(d)!r} && echo alive\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("alive", result.stdout)
        self.assertEqual(oct(d.stat().st_mode & 0o777), "0o700")

    def test_a_normal_update_refuses_while_an_update_was_interrupted(self):
        orphan = self.orphan(owner="pid=999999\nstart=1\nboot=x\n", active="")
        result = self.run_lib("refuse_interrupted_stack_transaction\necho went-on\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("went-on", result.stdout)
        self.assertIn("--recover-interrupted", result.stderr)
        self.assertIn(str(orphan), result.stderr)
        clean = self.run_lib("rm -rf %r\nrefuse_interrupted_stack_transaction\necho went-on\n" % str(orphan))
        self.assertIn("went-on", clean.stdout)

    def test_nothing_to_recover(self):
        result = self.run_lib("recover_interrupted_stack_transaction\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no interrupted update", result.stdout)

    def test_an_update_stopped_before_changing_anything_is_just_cleared(self):
        orphan = self.orphan(root_transaction=ROOT_TXN + "\n")
        result = self.run_lib("recover_interrupted_stack_transaction\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(orphan.exists())
        log = self.log.read_text()
        self.assertNotIn("rollback dir=", log)
        self.assertIn(f"remove-root {ROOT_TXN}", log)

    def test_an_active_update_is_rolled_back_from_its_recorded_state(self):
        token = "ab" * 16
        orphan = self.orphan(root_transaction=ROOT_TXN + "\n", active="",
                             native_transaction=token + "\n")
        result = self.run_lib("recover_interrupted_stack_transaction\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        log = self.log.read_text()
        self.assertIn(f"rollback dir={orphan} root={ROOT_TXN} native=1:{token}", log)
        self.assertIn(f"remove-root {ROOT_TXN}", log)
        self.assertLess(log.index("lock"), log.index("rollback"))
        self.assertFalse(orphan.exists())
        self.assertIn("restored the installation", result.stdout)

    def test_a_failed_recovery_keeps_the_data_and_hands_over_to_the_manual_procedure(self):
        orphan = self.orphan(root_transaction=ROOT_TXN + "\n", active="")
        result = self.run_lib("recover_interrupted_stack_transaction\n", ROLLBACK_RC="1")
        self.assertEqual(result.returncode, 70)
        self.assertTrue(orphan.exists())
        reason = (orphan / "failure-reason").read_text()
        self.assertIn("rollback-complete: no", reason)
        self.assertNotIn("remove-root", self.log.read_text())
        after = self.run_lib("interrupted_stack_transactions\n")
        self.assertEqual(after.stdout.strip(), "", "a reported failure no longer blocks updates")

    def test_a_committed_update_finishes_its_cleanup_without_rolling_back(self):
        token = "cd" * 16
        orphan = self.orphan(root_transaction=ROOT_TXN + "\n", active="", committed="",
                             native_transaction=token + "\n")
        result = self.run_lib("recover_interrupted_stack_transaction\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        log = self.log.read_text()
        self.assertNotIn("rollback dir=", log)
        self.assertIn(f"finish {token}", log)
        self.assertFalse(orphan.exists())

    def test_unsafe_records_and_ambiguity_are_refused(self):
        self.orphan("stack-rollback.Unsafe", root_transaction="/etc\n", active="")
        result = self.run_lib("recover_interrupted_stack_transaction\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe root recovery path", result.stderr)
        subprocess.run(["rm", "-rf", str(self.state / "stack-rollback.Unsafe")])
        self.orphan("stack-rollback.One001", active="", root_transaction=ROOT_TXN + "\n")
        self.orphan("stack-rollback.Two002", active="", root_transaction=ROOT_TXN + "\n")
        result = self.run_lib("recover_interrupted_stack_transaction\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("several interrupted updates", result.stderr)
        self.assertNotIn("rollback dir=", self.log.read_text())

    def test_kept_creations_survive_recovery(self):
        orphan = self.orphan(root_transaction=ROOT_TXN + "\n", active="")
        (orphan / "kilix95.created").mkdir()
        result = self.run_lib(
            "rollback_stack_transaction() { echo \"rollback dir=$_STACK_TXN_DIR\" >>\"$LOG\"; _STACK_TXN_RETAIN=1; }\n"
            "recover_interrupted_stack_transaction\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("could not compare /etc/pleb/closure.env with the installation", result.stderr)
        self.assertTrue((orphan / "kilix95.created").is_dir(), "what the rollback kept stays kept")
        self.assertIn("rollback-complete: yes", (orphan / "failure-reason").read_text())
        self.assertNotIn("remove-root", self.log.read_text())
        self.assertEqual(self.run_lib("interrupted_stack_transactions\n").stdout.strip(), "")

    RC5_NOTE = ("exit-status: interrupted (left by an earlier updater)\n"
                "when: 2026-10-06T15:50:00Z\nrollback-complete: no\n"
                "recover-with: plebian-os-select-closure --rollback\n"
                "then: plebian-os-update --restart\n")

    def assert_current_note(self, d):
        note = (d / "failure-reason").read_text()
        self.assertIn("blocks-updates: no", note)
        self.assertIn("advice: plebian-os-update --revalidate-current reinstalls the selected", note)
        self.assertNotIn("--rollback", note, "rollback advice is wrong once the machine updated since")

    def test_earlier_updaters_leftovers_never_block_and_are_kept(self):
        # The laptop's RC5 update: six such directories from August and
        # September refused the update even though it had updated since.
        old = [self.orphan(f"stack-rollback.Old00{i}", owner=None) for i in (1, 2, 3)]
        (old[0] / "kilix.head").write_text("0123abc\n")
        result = self.run_lib("note_legacy_stack_leftovers\n"
                              "refuse_interrupted_stack_transaction\necho went-on\n")
        self.assertIn("went-on", result.stdout, result.stderr)
        self.assertIn("do not block updates", result.stderr)
        for d in old:
            self.assertTrue(d.is_dir(), "kept for inspection")
            self.assert_current_note(d)
        self.assertTrue((old[0] / "kilix.head").exists())
        again = self.run_lib("note_legacy_stack_leftovers\n")
        self.assertNotIn("kept an earlier updater", again.stderr, "noted once, not every run")
        log = self.log.read_text()
        self.assertNotIn("rollback dir=", log)
        self.assertNotIn("remove-root", log)

    def test_rc5_notes_with_rollback_advice_are_rewritten_and_others_left(self):
        rc5 = self.orphan("stack-rollback.Rc5001", owner=None, failure_reason=self.RC5_NOTE)
        theirs = self.orphan("stack-rollback.Old001", owner=None,
                             failure_reason="exit-status: 1\nrecover-with: plebian-os-select-closure --rollback\n")
        current = self.orphan("stack-rollback.Cur001", owner=None)
        self.run_lib("note_legacy_stack_leftovers\n")
        before = (current / "failure-reason").read_bytes()
        result = self.run_lib("note_legacy_stack_leftovers\n")
        self.assert_current_note(rc5)
        self.assertEqual((theirs / "failure-reason").read_text(),
                         "exit-status: 1\nrecover-with: plebian-os-select-closure --rollback\n",
                         "an old updater's own failure report is its record; never rewritten")
        self.assertEqual((current / "failure-reason").read_bytes(), before)
        self.assertNotIn("kept an earlier updater", result.stderr)

    def test_recovery_notes_leftovers_and_recovers_only_an_owned_update(self):
        old = self.orphan("stack-rollback.Old001", owner=None)
        mine = self.orphan("stack-rollback.New002", root_transaction=ROOT_TXN + "\n", active="")
        result = self.run_lib("recover_interrupted_stack_transaction\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"rollback dir={mine} ", self.log.read_text())
        self.assertFalse(mine.exists())
        self.assert_current_note(old)
        alone = self.run_lib("recover_interrupted_stack_transaction\n")
        self.assertEqual(alone.returncode, 0, alone.stderr)
        self.assertIn("no interrupted update to recover", alone.stdout)
        self.assertEqual(self.run_lib("interrupted_stack_transactions\n").stdout.strip(), "")

    INSTALLED = ("PLEBIAN_OS_RELEASE=0.2.2\nPLEBIAN_OS_REF=1111111111111111aaaa\n"
                 "PLEB_REF=p1\nKILIX_REF=k1\nKILIX95_REF=n1\n")

    def recover_with_installed(self, selected, installed=INSTALLED):
        versions = self.tmp / "versions.env"
        versions.unlink(missing_ok=True)
        if installed is not None:
            versions.write_text(installed)
        return self.run_lib(selected + "recover_interrupted_stack_transaction\n",
                            PLEBIAN_OS_INSTALLED_VERSIONS=str(versions))

    def test_recovery_states_whether_the_selection_matches_the_installation(self):
        same = "PLEBIAN_OS_RELEASE=0.2.2\nPLEBIAN_OS_REF=1111111111111111aaaa\nPLEB_REF=p1\nKILIX_REF=k1\nKILIX95_REF=n1\n"
        newer = same.replace("1111111111111111aaaa", "87991f7b70ab41cb5105").replace("k1", "k2")
        for branch in ("rolled back", "cleared"):
            with self.subTest(branch=branch):
                markers = {"active": ""} if branch == "rolled back" else {}
                self.orphan(f"stack-rollback.{branch[:4]}A1", root_transaction=ROOT_TXN + "\n", **markers)
                agree = self.recover_with_installed(same)
                self.assertEqual(agree.returncode, 0, agree.stderr)
                self.assertIn("the selected closure matches the installation (release 0.2.2)", agree.stdout)
                self.assertNotIn("Choose one", agree.stderr)
                self.orphan(f"stack-rollback.{branch[:4]}B1", root_transaction=ROOT_TXN + "\n", **markers)
                split = self.recover_with_installed(newer)
                self.assertIn("selects release 0.2.2 (Plebian-OS 87991f7b70ab),", split.stderr)
                self.assertIn("but release 0.2.2 (Plebian-OS 111111111111) is installed", split.stderr)
                self.assertIn("plebian-os-update --revalidate-current   installs the selected release",
                              split.stderr)
                self.assertIn("plebian-os-select-closure --rollback     selects the previous closure again",
                              split.stderr)
        self.orphan("stack-rollback.NoVer1", root_transaction=ROOT_TXN + "\n")
        unknown = self.recover_with_installed(newer, installed=None)
        self.assertIn("could not compare /etc/pleb/closure.env with the installation", unknown.stderr)

    def test_a_dry_run_rollback_is_refused_rather_than_performed(self):
        root = self.tmp / "root"
        (root / "etc/pleb").mkdir(parents=True)
        (root / "etc/pleb/session.env").write_text("KEEP=1\n")
        env = {"HOME": str(self.tmp / "home"), "PATH": os.environ["PATH"], "LANG": "C",
               "PLEBIAN_OS_CLOSURE_TEST_ROOT": str(root)}
        done = subprocess.run([str(ROOT / "provision" / "plebian-os-select-closure.sh"),
                               "--rollback", "--dry-run"], env=env, text=True,
                              capture_output=True, check=False, timeout=60)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("--dry-run applies to a selection only", done.stderr)
        self.assertEqual((root / "etc/pleb/session.env").read_text(), "KEEP=1\n")

    def test_a_leftover_holding_a_native_transaction_says_when_it_can_block(self):
        d = self.orphan("stack-rollback.Nat001", owner=None, native_transaction="ab" * 16 + "\n")
        self.run_lib("note_legacy_stack_leftovers\n")
        note = (d / "failure-reason").read_text()
        self.assertIn(f"blocks-updates: no, unless its native transaction {'ab' * 16} is still active", note)
        self.assertIn("plebian-os-native-runtime status", note)

    def test_the_note_dates_the_leftover_not_itself(self):
        d = self.orphan("stack-rollback.Aug001", owner=None)
        for name in ("kilix.head", "pleb.ref"):
            (d / name).write_text("x\n")
        os.utime(d / "kilix.head", (1754820000, 1754820000))      # 2025-08-10T10:00:00Z
        os.utime(d / "pleb.ref", (1754906400, 1754906400))        # 2025-08-11T10:00:00Z
        self.run_lib("note_legacy_stack_leftovers\n")
        self.assertIn("contents-last-modified: 2025-08-11T10:00:00Z", (d / "failure-reason").read_text())

    def test_the_note_never_writes_through_a_link_or_destroys_an_old_note(self):
        outside = self.tmp / "outside.txt"
        linked = self.orphan("stack-rollback.Link01", owner=None)
        (linked / "failure-reason").symlink_to(outside)
        self.run_lib("note_legacy_stack_leftovers\n")
        self.assertFalse(outside.exists(), "a failure-reason link is never followed")
        locked = self.orphan("stack-rollback.Lock01", owner=None, failure_reason=self.RC5_NOTE)
        locked.chmod(0o500)
        self.addCleanup(locked.chmod, 0o700)
        self.run_lib("note_legacy_stack_leftovers\n")
        self.assertEqual((locked / "failure-reason").read_text(), self.RC5_NOTE,
                         "a write that cannot complete leaves the old note whole")
        self.assertFalse((locked / "failure-reason.new").exists())
        target = self.tmp / "elsewhere"
        target.mkdir()
        (self.state / "stack-rollback.Dirlnk").symlink_to(target)
        self.run_lib("note_legacy_stack_leftovers\n")
        self.assertFalse((target / "failure-reason").exists(), "a linked leftover is never noted")

    def test_an_rc5_transaction_that_lost_its_owner_still_blocks(self):
        for marker in ("active", "committed", "committed.prepared", "root-transaction",
                       "native-finish-pending"):
            with self.subTest(marker=marker):
                d = self.orphan(f"stack-rollback.M{marker[:5]}", owner=None)
                (d / marker).write_text("")
                listed = self.run_lib("interrupted_stack_transactions\n").stdout.split()
                if marker == "native-finish-pending":
                    self.assertNotIn(str(d), listed, "committed; native cleanup only")
                else:
                    self.assertIn(str(d), listed)
                self.run_lib("note_legacy_stack_leftovers\n")
                self.assertFalse((d / "failure-reason").exists(), "not an earlier updater's")
                subprocess.run(["rm", "-rf", str(d)], check=True)

    def test_each_kept_leftover_is_named(self):
        old = [self.orphan(f"stack-rollback.Nam00{i}", owner=None) for i in (1, 2)]
        result = self.run_lib("note_legacy_stack_leftovers\n")
        for d in old:
            self.assertIn(f"kept an earlier updater's leftover (no progress recorded): {d}", result.stderr)

    def test_a_normal_update_notes_leftovers_before_deciding_to_refuse(self):
        text = UPDATE_PATH.read_text()
        self.assertIn("\nnote_legacy_stack_leftovers\nrefuse_interrupted_stack_transaction\n", text)

    def test_the_selector_copies_the_updaters_detection_exactly(self):
        import re
        select = (ROOT / "provision" / "plebian-os-select-closure.sh").read_text()
        update = UPDATE_PATH.read_text()
        for name in ("process_start_ticks", "stack_transaction_owner_alive",
                     "interrupted_stack_transactions"):
            pattern = re.compile(r"^%s\(\) \{\n.*?^\}\n" % name, re.S | re.M)
            self.assertEqual(pattern.search(select).group(0), pattern.search(update).group(0), name)

    def test_the_selector_refuses_to_pin_a_release_while_an_update_awaits_recovery(self):
        home = self.tmp / "home"
        state = home / ".local/gpu_terminal/pleb/state"
        state.mkdir(parents=True)
        (state / "stack-rollback.Dead01").mkdir()
        (state / "stack-rollback.Dead01" / "owner").write_text("pid=999999\nstart=1\nboot=gone\n")
        (state / "stack-rollback.Old001").mkdir()              # an earlier updater's: ignored
        root = self.tmp / "root"
        (root / "etc/pleb").mkdir(parents=True)
        (root / "etc/pleb/session.env").write_text("")
        env = {"HOME": str(home), "PATH": os.environ["PATH"], "LANG": "C",
               "PLEBIAN_OS_CLOSURE_TEST_ROOT": str(root)}
        select = str(ROOT / "provision" / "plebian-os-select-closure.sh")
        run = lambda *a: subprocess.run([select, *a], env=env, text=True,
                                        capture_output=True, check=False, timeout=60)
        for args in (("--rollback",), ("0.2.2", "--offline")):
            refused = run(*args)
            self.assertNotEqual(refused.returncode, 0, args)
            self.assertIn("plebian-os-update --recover-interrupted", refused.stderr, args)
            self.assertIn("stack-rollback.Dead01", refused.stderr)
            self.assertNotIn("stack-rollback.Old001", refused.stderr)
        self.assertEqual(sorted(p.name for p in (root / "etc/pleb").iterdir()), ["session.env"],
                         "nothing was written")
        dry = run("0.2.2", "--offline", "--dry-run")
        self.assertIn("a real selection would be refused", dry.stderr)
        subprocess.run(["rm", "-rf", str(state / "stack-rollback.Dead01")], check=True)
        clear = run("--rollback")
        self.assertNotIn("--recover-interrupted", clear.stderr, "no pending recovery, no refusal")
        # session.env may move Pleb's storage; the selector looks where the updater looks.
        moved = self.tmp / "elsewhere/state"
        (moved / "stack-rollback.Dead02").mkdir(parents=True)
        (moved / "stack-rollback.Dead02" / "owner").write_text("pid=999999\nstart=1\nboot=gone\n")
        (root / "etc/pleb/session.env").write_text(f"PLEB_STATE_HOME={moved}\n")
        relocated = run("--rollback")
        self.assertIn("stack-rollback.Dead02", relocated.stderr)
        self.assertIn("--recover-interrupted", relocated.stderr)
        # The updater's precedence: the caller's environment, then session.env and
        # closure.env sourced over it, then the defaults.
        def found_in(where, session_text, **env_extra):
            (where / "stack-rollback.Dead03").mkdir(parents=True, exist_ok=True)
            (where / "stack-rollback.Dead03" / "owner").write_text("pid=999999\nstart=1\nboot=gone\n")
            (root / "etc/pleb/session.env").write_text(session_text)
            env.update(env_extra)
            try:
                return "stack-rollback.Dead03" in run("--rollback").stderr
            finally:
                for key in env_extra:
                    env.pop(key, None)
                subprocess.run(["rm", "-rf", str(where / "stack-rollback.Dead03")], check=True)
        mine, theirs = self.tmp / "mine/state", self.tmp / "theirs/state"
        self.assertTrue(found_in(theirs, f"PLEB_STATE_HOME={theirs}\n", PLEB_STATE_HOME=str(mine)),
                        "an unguarded session.env assignment wins, as when the updater sources it")
        self.assertTrue(found_in(mine, f'if [ -z "${{PLEB_STATE_HOME+x}}" ]; then PLEB_STATE_HOME={theirs}; fi\n',
                                 PLEB_STATE_HOME=str(mine)), "a guarded one keeps the caller's value")
        self.assertTrue(found_in(home / ".local/gpu_terminal/pleb/state", "", PLEB_STATE_HOME=""),
                        "an empty value means the default")
        self.assertTrue(found_in(home / "custom/state", 'PLEB_STORAGE_HOME="$HOME/custom"\n'),
                        "session.env expressions see the caller's environment")
        (root / "etc/pleb/closure.env").write_text(f"PLEB_STORAGE_HOME={self.tmp / 'closure'}\n")
        self.assertTrue(found_in(self.tmp / "closure/state", ""),
                        "closure.env is sourced after session.env, as the updater does")
        (root / "etc/pleb/closure.env").unlink()

    def test_an_active_update_without_a_root_path_is_refused(self):
        orphan = self.orphan(active="")
        result = self.run_lib("recover_interrupted_stack_transaction\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no root recovery path", result.stderr)
        self.assertNotIn("rollback dir=", self.log.read_text())
        self.assertTrue(orphan.exists())

    def test_the_markers_are_written_where_a_kill_can_leave_them(self):
        text = UPDATE_PATH.read_text()
        begin = text[text.index("\nbegin_stack_transaction() {"):]
        begin = begin[:begin.index("\n}\n")]
        self.assertLess(begin.index("record_stack_transaction_owner"), begin.index("record_stack_checkout"))
        self.assertLess(begin.index('"$_STACK_TXN_DIR/root-transaction"'), begin.index("_STACK_TXN_ACTIVE=1"))
        self.assertLess(begin.index('"$_STACK_TXN_DIR/active"'), begin.index("_STACK_TXN_ACTIVE=1"))
        # active must exist before the first change to the installation
        self.assertLess(begin.index('"$_STACK_TXN_DIR/active"'), begin.index("begin_kilix_engine_mutation"))
        self.assertLess(begin.index('"$_STACK_TXN_DIR/active"'),
                        begin.index('rm -f -- "$PLEB_STATE_HOME/kilix-fork-built-ref"'))
        # the cleanup trap is armed before anything that can fail
        self.assertLess(begin.index("trap stack_transaction_cleanup EXIT"),
                        begin.index("record_stack_transaction_owner"))
        self.assertIn('"$_STACK_TXN_DIR/committed.prepared"', begin)
        commit = text[text.index("\ncommit_stack_transaction() {"):]
        commit = commit[:commit.index("\n}\n")]
        self.assertLess(commit.index("_STACK_TXN_COMMITTED=1"), commit.index('"$_STACK_TXN_DIR/committed"'))
        self.assertIn('mv -f -- "$_STACK_TXN_DIR/committed.prepared" "$_STACK_TXN_DIR/committed"', commit)
        self.assertIn('"$_STACK_TXN_DIR/native-finish-pending"', commit)
        main = text.index('if [ "${PLEBIAN_OS_UPDATE_TEST_LIBRARY_ONLY:-0}" = 1 ]; then\n    return 0')
        self.assertLess(text.index("\n    recover_interrupted_stack_transaction\n", main),
                        text.index("\nselect_latest_release_if_needed\n", main))
        self.assertLess(text.index("\nrefuse_interrupted_stack_transaction\n", main),
                        text.index("\nselect_latest_release_if_needed\n", main))
        self.assertIn("--recover-interrupted) recover_interrupted=1 ;;", text)


if __name__ == "__main__":
    unittest.main()
