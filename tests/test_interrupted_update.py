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
        env.update({"HOME": str(self.tmp / "home"), "LOG": str(self.log), **extra})
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
        self.assertEqual(listed, {str(dead), str(rebooted), str(reused), str(legacy)})
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
        self.assertTrue((orphan / "kilix95.created").is_dir(), "what the rollback kept stays kept")
        self.assertIn("rollback-complete: yes", (orphan / "failure-reason").read_text())
        self.assertNotIn("remove-root", self.log.read_text())
        self.assertEqual(self.run_lib("interrupted_stack_transactions\n").stdout.strip(), "")

    def test_an_earlier_updaters_leftover_is_never_deleted(self):
        orphan = self.orphan(owner=None)
        (orphan / "kilix.head").write_text("0123abc\n")
        result = self.run_lib("recover_interrupted_stack_transaction\n")
        self.assertEqual(result.returncode, 70)
        self.assertTrue((orphan / "kilix.head").exists())
        self.assertIn("plebian-os-select-closure --rollback", (orphan / "failure-reason").read_text())
        log = self.log.read_text()
        self.assertNotIn("rollback dir=", log)
        self.assertNotIn("remove-root", log)

    def test_several_earlier_leftovers_are_all_kept_and_stop_blocking(self):
        old = [self.orphan(f"stack-rollback.Old00{i}", owner=None) for i in (1, 2)]
        blocked = self.run_lib("refuse_interrupted_stack_transaction\necho went-on\n")
        self.assertNotIn("went-on", blocked.stdout)
        result = self.run_lib("recover_interrupted_stack_transaction\n")
        self.assertEqual(result.returncode, 70, result.stderr)
        self.assertNotIn("several interrupted updates", result.stderr)
        for d in old:
            self.assertIn("rollback-complete: no", (d / "failure-reason").read_text())
        after = self.run_lib("refuse_interrupted_stack_transaction\necho went-on\n")
        self.assertIn("went-on", after.stdout, after.stderr)
        self.assertNotIn("rollback dir=", self.log.read_text())

    def test_an_earlier_leftover_beside_an_interrupted_update_does_not_hide_it(self):
        old = self.orphan("stack-rollback.Old001", owner=None)
        mine = self.orphan("stack-rollback.New002", root_transaction=ROOT_TXN + "\n", active="")
        result = self.run_lib("recover_interrupted_stack_transaction\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"rollback dir={mine} ", self.log.read_text())
        self.assertFalse(mine.exists())
        self.assertTrue((old / "failure-reason").exists())
        self.assertEqual(self.run_lib("interrupted_stack_transactions\n").stdout.strip(), "")

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
