"""Old published Pleb records `selecting` before the new selector starts.

Commit 49fc7554a01b30e33fd1a8f12e038906830bc7fe then always calls
`--rollback` on the next run. If that call arrives before selection-pending
exists, restoring the newest older record moves the machine back a release.
These tests run that published recovery function against this selector.
"""

import os
import signal
import subprocess
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from test_closure_selection import SELECT, ClosureSelectionTests


OLD_PLEB = "49fc7554a01b30e33fd1a8f12e038906830bc7fe"
OLD_CLOSURE_BLOB = "67a0e01b11f02cc03b4e42ab8afb8a1eea5c1ed3"
PLEB_REPO = Path("/home/pleb/gpu_terminal/worktrees/rc9-pleb-hop")
PREBUILT_SHA = "bc230142b2bd27f2a4bf1b1b67575f3d397a4ea2cc83f4ac2b912c306a939693"

OLD_DRIVER = textwrap.dedent(
    """\
    set -euo pipefail
    root="$1"
    mode="$2"
    die() { printf '%s\\n' "$*" >&2; exit 1; }
    log() { printf '%s\\n' "$*"; }
    warn() { printf '%s\\n' "$*" >&2; }
    err() { printf '%s\\n' "$*" >&2; }
    ensure_pleb_private_storage() {
        mkdir -p -- "$PLEB_CACHE_HOME" "$PLEB_STATE_HOME"
    }
    _release_update_lock() { :; }
    # shellcheck source=/dev/null
    . "$root/lib/closure.sh"
    case "$mode" in
        prepare)
            _pleb_prepare_target_selector "$3" 0 "v$3"
            _pleb_record_active_selector selecting
            printf 'tag=%s\\n' "$_PLEB_HOP_TAG_OBJECT"
            ;;
        recover)
            pleb_recover_incomplete_release_hop
            printf 'result=%s\\n' "${_PLEB_HOP_RECOVERY_RESULT:-}"
            ;;
        *) die "unknown old-pleb mode: $mode" ;;
    esac
    """
)


class EarlyHopTests(unittest.TestCase):
    def _helper(self) -> ClosureSelectionTests:
        return ClosureSelectionTests(
            "test_rollback_restores_the_previous_closure_byte_for_byte")

    @staticmethod
    def _tree_bytes(root: Path) -> dict:
        found = {}
        if not root.exists():
            return found
        for path in sorted(root.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            found[str(path.relative_to(root))] = path.read_bytes()
        return found

    def _extract_old_pleb(self, dest: Path) -> None:
        blob = subprocess.run(
            ["git", "-C", str(PLEB_REPO), "rev-parse",
             f"{OLD_PLEB}:lib/closure.sh"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        self.assertEqual(blob, OLD_CLOSURE_BLOB, "published old Pleb blob moved")
        archive = subprocess.run(
            ["git", "-C", str(PLEB_REPO), "archive", OLD_PLEB, "lib/closure.sh"],
            capture_output=True, check=True,
        )
        dest.mkdir(parents=True)
        subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout,
                       check=True)
        text = (dest / "lib/closure.sh").read_text()
        self.assertIn("pleb_recover_incomplete_release_hop()", text)
        self.assertIn(
            "interrupted selector left no restorable selected closure", text)
        self.assertNotIn("baseline", text)

    def _hop_repo(self, base: Path) -> Path:
        """A local tag whose selector is this worktree's selector."""
        repo = base / "hop-target"
        (repo / "provision").mkdir(parents=True)
        (repo / "releases").mkdir()
        (repo / "VERSION").write_text("0.1.9\n")
        (repo / "releases" / "0.1.9.env").write_text(
            "PLEBIAN_OS_VERSION=0.1.9\n")
        script = repo / "provision" / "plebian-os-select-closure.sh"
        script.write_bytes(SELECT.read_bytes())
        script.chmod(0o755)
        git = ["git", "-C", str(repo)]
        subprocess.run(git + ["init", "-q"], check=True)
        subprocess.run(git + ["config", "user.email", "t@example.invalid"],
                       check=True)
        subprocess.run(git + ["config", "user.name", "t"], check=True)
        subprocess.run(git + ["add", "-A"], check=True)
        subprocess.run(git + ["commit", "-qm", "0.1.9"], check=True)
        subprocess.run(git + ["tag", "-a", "v0.1.9", "-m", "v0.1.9"],
                       check=True)
        return repo

    def _old_env(self, base: Path, root: Path, repo: Path, version: str) -> dict:
        state = base / "home/.local/gpu_terminal/pleb/state"
        cache = base / "home/.local/gpu_terminal/pleb/cache"
        kilix = base / "empty-kilix"
        kilix95 = base / "empty-kilix95"
        kilix.mkdir(exist_ok=True)
        kilix95.mkdir(exist_ok=True)
        return {
            "HOME": str(base / "home"),
            "PATH": os.environ["PATH"],
            "LANG": "C",
            "TMPDIR": str(base),
            "GPU_TERMINAL_HOME": str(base / "home/.local/gpu_terminal"),
            "GPU_TERMINAL_SOURCE_HOME": str(base / "home/.local/gpu_terminal/sources"),
            "PLEBIAN_OS_DIR": str(repo),
            "PLEB_ROOT": str(root),
            "PLEB_STATE_HOME": str(state),
            "PLEB_CACHE_HOME": str(cache),
            "PLEBIAN_OS_REPO": str(repo),
            "PLEBIAN_OS_VERSION": version,
            "PLEBIAN_OS_MANAGED_INSTALL": "1",
            "PLEB_ENV_SYSTEM": str(base / "root/etc/pleb/session.env"),
            "PLEB_CLOSURE_SYSTEM": str(base / "root/etc/pleb/closure.env"),
            "PLEBIAN_OS_RECOVERY_BASE": str(base / "root/var/lib/plebian-os"),
            "PLEBIAN_OS_SELECTOR_DST": str(
                base / "root/usr/local/bin/plebian-os-select-closure"),
            "PLEBIAN_OS_UPDATER_DST": str(
                base / "root/usr/local/bin/plebian-os-update"),
            "KILIX_DIR": str(kilix),
            "KILIX95_DIR": str(kilix95),
            "PLEBIAN_OS_CLOSURE_TEST_ROOT": str(base / "root"),
            "PLEB_TEST_UPDATER_LOG": str(base / "updater.log"),
        }

    def _run_old(self, base: Path, env: dict, mode: str, target: str = ""):
        driver = base / "old-pleb-driver.sh"
        driver.write_text(OLD_DRIVER)
        args = ["bash", str(driver), env["PLEB_ROOT"], mode]
        if target:
            args.append(target)
        return subprocess.run(args, env=env, capture_output=True, text=True,
                              check=False)

    def _stop_private_group(self, proc: subprocess.Popen, child: int = 0) -> None:
        if proc.poll() is None:
            try:
                os.kill(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if child and Path(f"/proc/{child}").exists():
            try:
                os.kill(child, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

    def _assert_parent_death_stops_before_marker(self, base: Path) -> None:
        fifo = base / "hold.fifo"
        os.mkfifo(fifo)
        env = {
            "HOME": str(base / "home"),
            "PATH": os.environ["PATH"],
            "LANG": "C",
            "TMPDIR": str(base),
            "PLEBIAN_OS_CLOSURE_TEST_ROOT": str(base / "root"),
            "PLEBIAN_OS_CLOSURE_LAYOUT": "split",
            "PLEBIAN_OS_SELECT_TEST_HOLD_BEFORE_PENDING": str(fifo),
            "PLEBIAN_OS_SELECT_TEST_SKIP_COMPONENT_ANCESTRY": "1",
        }
        log_path = base / "held-selector.log"
        log_f = open(log_path, "w")
        proc = subprocess.Popen(
            ["bash", "-c", '"$@"; wait', "bash", str(SELECT), "0.1.8",
             "--offline"],
            cwd=str(base),
            env=env,
            start_new_session=True,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            text=True,
        )
        child = 0

        def cleanup():
            self._stop_private_group(proc, child)
            log_f.close()

        self.addCleanup(cleanup)
        pid_path = Path(str(fifo) + ".pid")
        deadline = time.time() + 5
        while time.time() < deadline and not pid_path.exists():
            if proc.poll() is not None:
                self.fail("selector exited before the hold:\n"
                          + log_path.read_text()[-2000:])
            time.sleep(0.05)
        self.assertTrue(pid_path.exists(),
                        "selector did not reach the pre-marker hold:\n"
                        + log_path.read_text()[-2000:])
        child = int(pid_path.read_text().strip())
        status = Path(f"/proc/{child}/status").read_text()
        ppid = int(next(line for line in status.splitlines()
                        if line.startswith("PPid:")).split()[1])
        self.assertEqual(ppid, proc.pid)
        os.kill(proc.pid, signal.SIGKILL)
        deadline = time.time() + 3
        while time.time() < deadline and Path(f"/proc/{child}").exists():
            time.sleep(0.05)
        self.assertFalse(
            Path(f"/proc/{child}").exists(),
            "selector kept running after its parent died")
        proc.wait(timeout=5)
        pending = (base / "home/.local/gpu_terminal/pleb/state"
                   / "selection-pending")
        self.assertFalse(pending.exists())

    def test_early_interruption_does_not_select_the_older_record(self):
        helper = self._helper()
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env_path = helper._machine(base)
            helper._source(base)
            notes = base / "home/user-notes.txt"
            notes.parent.mkdir(parents=True, exist_ok=True)
            notes.write_bytes(b"notes-stay\n")
            before = env_path.read_bytes()
            selected = helper._run(
                base, "0.1.8", "--offline",
                env_extra={"PLEBIAN_OS_CLOSURE_LAYOUT": "split"})
            self.assertEqual(selected.returncode, 0, selected.stderr)
            installed = env_path.read_bytes()
            self.assertNotEqual(installed, before)
            closure = base / "root/etc/pleb/closure.env"
            closure_bytes = closure.read_bytes() if closure.is_file() else None
            records = helper._recovery_records(base)
            self.assertEqual(len(records), 1)
            self.assertIn("selection_tag=", (records[0] / "meta").read_text())
            older = self._tree_bytes(records[0])
            self.assertNotIn("restored", older)
            record_name = records[0].name

            self._assert_parent_death_stops_before_marker(base)
            self.assertEqual(env_path.read_bytes(), installed)
            self.assertEqual(self._tree_bytes(
                base / "root/var/lib/plebian-os" / record_name), older)
            self.assertEqual(notes.read_bytes(), b"notes-stay\n")
            self.assertEqual(len(helper._recovery_records(base)), 1)

            root = base / "old-pleb"
            self._extract_old_pleb(root)
            repo = self._hop_repo(base)
            old_env = self._old_env(base, root, repo, "0.1.8")
            prepared = self._run_old(base, old_env, "prepare", "0.1.9")
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            self.assertRegex(prepared.stdout, r"(?m)^tag=[0-9a-f]{40}$")
            phase = (Path(old_env["PLEB_STATE_HOME"]) / "release-hop" / "phase")
            self.assertEqual(phase.read_text(), "selecting\n")
            self.assertFalse((Path(old_env["PLEB_STATE_HOME"])
                              / "selection-pending").exists())

            recovered = self._run_old(base, old_env, "recover")
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            combined = recovered.stdout + recovered.stderr
            self.assertIn("result=unchanged", combined)
            self.assertIn("no restorable selected closure", combined)
            self.assertIn("refusing rollback", combined)
            self.assertNotIn("restored the previous closure", combined)
            self.assertEqual(env_path.read_bytes(), installed)
            if closure_bytes is None:
                self.assertFalse(closure.exists())
            else:
                self.assertEqual(closure.read_bytes(), closure_bytes)
            self.assertEqual(self._tree_bytes(
                base / "root/var/lib/plebian-os" / record_name), older)
            self.assertFalse((base / "root/var/lib/plebian-os" / record_name
                              / "restored").exists())
            self.assertEqual(notes.read_bytes(), b"notes-stay\n")
            state = Path(old_env["PLEB_STATE_HOME"]) / "release-hop"
            self.assertFalse((state / "active").exists())
            self.assertFalse((state / "phase").exists())

            manual = helper._run(
                base, "--rollback",
                env_extra={"PLEBIAN_OS_CLOSURE_LAYOUT": "split"})
            self.assertEqual(manual.returncode, 0, manual.stderr)
            self.assertEqual(env_path.read_bytes(), before)
            self.assertTrue((base / "root/var/lib/plebian-os" / record_name
                             / "restored").exists())
            self.assertEqual(notes.read_bytes(), b"notes-stay\n")

    def test_interrupted_after_change_restores_only_that_selection(self):
        helper = self._helper()
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env_path = helper._machine(base)
            helper._source(base)
            notes = base / "home/user-notes.txt"
            notes.parent.mkdir(parents=True, exist_ok=True)
            notes.write_bytes(b"notes-stay\n")
            extra = {"PLEBIAN_OS_CLOSURE_LAYOUT": "split"}
            first = helper._run(base, "0.1.8", "--offline", env_extra=extra)
            self.assertEqual(first.returncode, 0, first.stderr)
            installed = env_path.read_bytes()
            closure = base / "root/etc/pleb/closure.env"
            closure_bytes = closure.read_bytes()
            records = helper._recovery_records(base)
            self.assertEqual(len(records), 1)
            older_name = records[0].name
            older = self._tree_bytes(records[0])

            updater = base / "root/usr/local/bin/plebian-os-update"
            updater.write_text(
                "#!/bin/bash\n"
                "printf '%s\\n' \"$*\" >>\"${PLEB_TEST_UPDATER_LOG:-/dev/null}\"\n"
                "exit 0\n")
            updater.chmod(0o755)
            # Record names sort by UTC timestamp. A same-second pair would
            # order by the random suffix, so the second selection waits.
            time.sleep(1.1)
            manifest = base / "src/releases/0.1.8.env"
            manifest.write_text(manifest.read_text().replace(
                PREBUILT_SHA, "c" * 64, 1))
            git = ["git", "-C", str(base / "src")]
            subprocess.run(git + ["add", "-A"], check=True)
            subprocess.run(git + ["commit", "-qm", "mutate"], check=True)
            subprocess.run(git + ["tag", "-d", "v0.1.8"], check=True,
                           capture_output=True)
            subprocess.run(git + ["tag", "-a", "v0.1.8", "-m", "v0.1.8"],
                           check=True)

            interrupted = helper._run(
                base, "0.1.8", "--offline", env_extra=extra,
                fail_after="interrupt:applied")
            self.assertEqual(interrupted.returncode, 130, interrupted.stderr)
            # Split layout keeps operator session.env and moves the release
            # pins into closure.env. The interrupted selection replaced that
            # closure; session.env stays the operator file.
            self.assertEqual(env_path.read_bytes(), installed)
            changed_closure = closure.read_bytes()
            self.assertNotEqual(changed_closure, closure_bytes)
            pending = (base / "home/.local/gpu_terminal/pleb/state"
                       / "selection-pending")
            self.assertTrue(pending.is_file())
            records = helper._recovery_records(base)
            self.assertEqual(len(records), 2)
            self.assertEqual(self._tree_bytes(
                base / "root/var/lib/plebian-os" / older_name), older)

            root = base / "old-pleb"
            self._extract_old_pleb(root)
            old_env = self._old_env(base, root, base / "src", "0.1.8")
            prepared = self._run_old(base, old_env, "prepare", "0.1.8")
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            recovered = self._run_old(base, old_env, "recover")
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            combined = recovered.stdout + recovered.stderr
            self.assertIn("result=rolled-back", combined)
            self.assertNotIn("refusing rollback", combined)
            self.assertEqual(env_path.read_bytes(), installed)
            self.assertEqual(closure.read_bytes(), closure_bytes)
            self.assertNotEqual(closure.read_bytes(), changed_closure)
            self.assertEqual(self._tree_bytes(
                base / "root/var/lib/plebian-os" / older_name), older)
            self.assertFalse((base / "root/var/lib/plebian-os" / older_name
                              / "restored").exists())
            newer = [p for p in helper._recovery_records(base)
                     if p.name != older_name]
            self.assertEqual(len(newer), 1)
            self.assertTrue((newer[0] / "restored").is_file())
            self.assertEqual(notes.read_bytes(), b"notes-stay\n")
            self.assertIn("--revalidate-current",
                          (base / "updater.log").read_text())


if __name__ == "__main__":
    unittest.main()
