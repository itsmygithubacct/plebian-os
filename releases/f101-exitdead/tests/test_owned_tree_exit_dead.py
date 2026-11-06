"""EXIT_DEAD race tests for owned_tree.read_stat / OwnedTree (PREREG-COUNTER-AMENDMENT-ADDENDUM-EXITDEAD.md).

The module under test is the packet's candidate/owned_tree.py, or the path in $OWNED_TREE (for the unfixed and mutant controls).
Deterministic tests script /proc/PID/stat reads through the module-global `open`; the real-survivor and real-race tests use real
processes. Run in an owned pid namespace with its own /proc. Not part of the registered control plan.
"""
import builtins, errno, importlib.util, os, subprocess, sys, threading, time, unittest
from pathlib import Path

MODULE = os.environ.get('OWNED_TREE') or str(Path(__file__).resolve().parents[1] / 'candidate/owned_tree.py')
spec = importlib.util.spec_from_file_location('owned_tree', MODULE)
ot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ot)
# Captured verbatim on 6.12 (race_probe.py): a task in EXIT_DEAD after its signal struct is released.
XDEAD = '{pid} (python3) X 0 -1 -1 0 -1 4227084 855 0 0 0 0 0 0 0 20 0 0 0 {start} 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 17 11 0 0 0 0 0 0 0 0 0 0 0 0 0\n'


def live(pid, start, state='S', ppid=1, pgid=None):
    pgid = pid if pgid is None else pgid
    return (f'{pid} (python3) {state} {ppid} {pgid} {pgid} 0 -1 4194560 ' + '0 ' * 12 + f'{start} ' + '0 ' * 32 + '\n')


class Script:
    """Scripted reads for selected PIDs; every other path goes to the real /proc."""
    def __init__(self, plan):
        self.plan = {pid: list(items) for pid, items in plan.items()}
        self.reads = {pid: 0 for pid in plan}

    def __call__(self, path, mode='r'):
        pid = int(path.split('/')[2])
        if pid not in self.plan:
            return builtins.open(path, mode)
        self.reads[pid] += 1
        item = self.plan[pid][0] if len(self.plan[pid]) == 1 else self.plan[pid].pop(0)
        if isinstance(item, int):
            raise OSError(item, os.strerror(item))
        data = item.encode()

        class Handle:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n): return data[:n]
        return Handle()


class Scripted(unittest.TestCase):
    def tearDown(self):
        ot.__dict__.pop('open', None)

    def use(self, plan):
        script = Script(plan)
        ot.open = script
        return script

    def test_exit_dead_then_gone_is_absent(self):
        self.use({4242: [XDEAD.format(pid=4242, start=100), errno.ENOENT]})
        self.assertIsNone(ot.read_stat(4242))

    def test_exit_dead_then_esrch_is_absent(self):
        self.use({4242: [XDEAD.format(pid=4242, start=100), XDEAD.format(pid=4242, start=100), errno.ESRCH]})
        self.assertIsNone(ot.read_stat(4242))

    def test_exit_dead_then_reused_pid_is_a_new_identity(self):
        self.use({4242: [XDEAD.format(pid=4242, start=100), live(4242, 200)]})
        tree = ot.OwnedTree(4242, {'state': 'S', 'ppid': 1, 'pgid': 4242, 'start': 100})
        rows, errors = {4242: ot.read_stat(4242)}, {}
        self.assertEqual(rows[4242]['start'], 200)
        self.assertEqual(tree.observe(rows, errors), {})          # start mismatch: the known identity is gone
        self.assertTrue(tree.observation_complete)
        self.assertEqual(tree.errors, [])

    def test_persistent_exit_dead_stays_an_error(self):
        script = self.use({4242: [XDEAD.format(pid=4242, start=100)]})
        with self.assertRaisesRegex(ValueError, 'invalid process stat for 4242'):
            ot.read_stat(4242)
        self.assertGreater(script.reads[4242], 1)

    def test_exit_dead_with_valid_fields_is_returned_as_before(self):
        self.use({4242: [live(4242, 100, state='X', ppid=7, pgid=4242)]})
        self.assertEqual(ot.read_stat(4242), {'state': 'X', 'ppid': 7, 'pgid': 4242, 'start': 100})

    def test_a_negative_pgid_on_a_non_exit_dead_row_is_an_error(self):
        self.use({4242: [live(4242, 100, state='R', pgid=-1)]})
        with self.assertRaises(ValueError):
            ot.read_stat(4242)

    def test_truncated_and_mismatched_stat_are_errors(self):
        for bad in (live(4242, 100)[:40], '', '4243' + live(4242, 100)[4:], live(4242, 100).replace(' S ', ' SS ')):
            with self.subTest(bad=bad[:30]):
                self.use({4242: [bad]})
                with self.assertRaises(ValueError):
                    ot.read_stat(4242)


class RealSurvivor(unittest.TestCase):
    """A real live owned process whose stat cannot be parsed must never be credited as torn down."""
    def test_unreadable_live_survivor_is_not_torn_down(self):
        child = subprocess.Popen(['sleep', '30'], start_new_session=True)
        try:
            time.sleep(0.05)
            tree = ot.OwnedTree(child.pid, ot.read_stat(child.pid))
            for bad in (live(child.pid, 1)[:40], XDEAD.format(pid=child.pid, start=1).replace(' X ', ' R ')):
                with self.subTest(bad=bad[:30]):
                    ot.open = Script({child.pid: [bad]})
                    try:
                        current = tree.refresh()
                    finally:
                        ot.__dict__.pop('open', None)
                    torn_down = tree.observation_complete and not current and not tree.errors
                    self.assertIsNone(child.poll())                 # it really is alive
                    self.assertFalse(torn_down, 'a live survivor with an unreadable stat was credited as absent')
        finally:
            child.kill()
            child.wait()


class RealRace(unittest.TestCase):
    """Short-lived real processes while the REAL snapshot() runs: no ValueError may come from an exiting process."""
    SECONDS = float(os.environ.get('RACE_SECONDS', '8'))

    def test_snapshot_never_errors_on_exiting_processes(self):
        stop = threading.Event()

        def spawn():
            while not stop.is_set():
                subprocess.run([sys.executable, '-c', 'import subprocess,sys;[subprocess.Popen([sys.executable,"-c","pass"]).wait() for _ in range(3)]'])
        worker = threading.Thread(target=spawn)
        worker.start()
        errors, snapshots = [], 0
        try:
            end = time.monotonic() + self.SECONDS
            while time.monotonic() < end:
                rows, errs = ot.snapshot()
                snapshots += 1
                errors += [e for e in errs.values() if 'invalid process stat' in e]
        finally:
            stop.set()
            worker.join()
        print(f'\n  real race: {snapshots} snapshots, {len(errors)} invalid-stat errors', file=sys.stderr)
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
