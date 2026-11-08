"""QMP pathname, isolation and detached lifetime regressions; no guest boots."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

BUILD = Path(__file__).resolve().parents[1] / "build"
sys.path.insert(0, str(BUILD))
import qemu_runtime as runtime
import build_vm_image as vm


class QmpRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="qmp-test-", dir="/tmp")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "vm"
        self.directory.mkdir(mode=0o700)

    def prepare(self, directory=None):
        directory = directory or self.directory
        endpoint = runtime.prepare_qmp(directory)
        self.addCleanup(runtime.cleanup_empty_runtime, directory)
        return endpoint

    def test_preview_driver_can_import_builder_by_filename(self):
        script = '''
import importlib.util, sys
spec = importlib.util.spec_from_file_location("preview_builder", sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
assert callable(module.qemu_start)
'''
        subprocess.run([sys.executable, "-c", script, str(BUILD / "build_vm_image.py")],
                       cwd=self.root, env={**os.environ, "PYTHONPATH": ""},
                       check=True, capture_output=True, timeout=10)

    def test_linux_boundary_counts_filesystem_bytes(self):
        for stem in ("a", "é"):
            base = str(self.root) + "/"
            remaining = 107 - len(os.fsencode(base))
            name = stem * (remaining // len(os.fsencode(stem)))
            name += "x" * (remaining - len(os.fsencode(name)))
            endpoint = Path(base + name)
            self.assertEqual(len(os.fsencode(endpoint)), 107)
            self.assertEqual(runtime.check_socket_path(endpoint), endpoint)
            with socket.socket(socket.AF_UNIX) as listener:
                listener.bind(str(endpoint))
            with self.assertRaises(ValueError):
                runtime.check_socket_path(Path(str(endpoint) + "x"))
            with socket.socket(socket.AF_UNIX) as listener:
                with self.assertRaises(OSError):
                    listener.bind(str(endpoint) + "x")

    def test_long_resolved_multibyte_storage_and_tmpdir_do_not_reach_qemu(self):
        directory = self.root / ("é" * 60) / "vm"
        directory.mkdir(mode=0o700, parents=True)
        alias = self.root / "alias"
        alias.symlink_to(directory, target_is_directory=True)
        with patch.dict(os.environ, {"TMPDIR": str(directory),
                                     "XDG_RUNTIME_DIR": str(directory)}):
            endpoint = self.prepare(alias.resolve())
        self.assertLessEqual(len(os.fsencode(endpoint)), 107)
        self.assertNotEqual(endpoint.parent, directory)
        self.assertEqual(endpoint.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(endpoint.parent.stat().st_uid, os.getuid())
        self.assertEqual(runtime.qmp_socket_path(directory), endpoint)
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(str(endpoint))
            listener.listen(1)
            for _ in range(2):
                with socket.socket(socket.AF_UNIX) as client:
                    client.connect(str(runtime.qmp_socket_path(directory)))
                    listener.accept()[0].close()
        endpoint.unlink()

    def test_private_xdg_is_used_and_qemu_option_commas_are_escaped(self):
        parent = self.root / "runtime,private"
        parent.mkdir(mode=0o700)
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(parent)}), \
                patch.object(vm, "run") as invoke:
            vm.qemu_start(self.config(), self.root / "installer.iso", self.directory)
        self.addCleanup(runtime.cleanup_empty_runtime, self.directory)
        endpoint = runtime.qmp_socket_path(self.directory)
        self.assertEqual(endpoint.parent.parent, parent)
        argv = invoke.call_args.args[0]
        self.assertEqual(argv[argv.index("-qmp") + 1],
                         f"unix:{str(endpoint).replace(',', ',,')},server=on,wait=off")

    def test_unsafe_or_symlinked_xdg_is_ignored(self):
        parent = self.root / "open"
        parent.mkdir(mode=0o755)
        parent.chmod(0o755)
        symlink = self.root / "link"
        symlink.symlink_to(self.directory, target_is_directory=True)
        nested = parent / "private"
        nested.mkdir(mode=0o700)
        parent.chmod(0o777)
        for candidate in (parent, nested, symlink, Path("relative")):
            with self.subTest(candidate=candidate), \
                    patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(candidate)}):
                endpoint = runtime.prepare_qmp(self.directory)
                self.assertNotEqual(endpoint.parent.parent, candidate.resolve())
                self.assertTrue(runtime.cleanup_empty_runtime(self.directory))
        with patch.object(runtime.os, "getuid", return_value=os.getuid() + 1):
            self.assertFalse(runtime._private_directory(self.directory))

    def test_concurrent_reservations_leave_only_one_owned_runtime(self):
        from concurrent.futures import ThreadPoolExecutor
        parent = self.root / "runtime"
        parent.mkdir(mode=0o700)
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(parent)}), \
                ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(runtime.prepare_qmp, self.directory) for _ in range(2)]
            endpoints = []
            for future in futures:
                try:
                    endpoints.append(future.result())
                except (RuntimeError, FileExistsError):
                    pass
        self.addCleanup(runtime.cleanup_empty_runtime, self.directory)
        self.assertEqual(len(endpoints), 1)
        self.assertEqual(list(parent.iterdir()), [endpoints[0].parent])
        self.assertEqual(runtime.qmp_socket_path(self.directory), endpoints[0])

    def test_no_safe_short_parent_fails_without_launch_state(self):
        parent = self.root / ("x" * 100)
        parent.mkdir(mode=0o700)
        with patch.object(runtime, "_runtime_parents", return_value=iter([parent])):
            with self.assertRaisesRegex(RuntimeError, "No safe short"):
                runtime.prepare_qmp(self.directory)
        self.assertEqual(list(parent.iterdir()), [])
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_different_vms_never_share_runtime_and_repeated_start_refuses(self):
        other = self.root / "another" / "vm"
        other.mkdir(mode=0o700, parents=True)
        first, second = self.prepare(), self.prepare(other)
        self.assertNotEqual(first, second)
        with self.assertRaisesRegex(RuntimeError, "fresh"):
            runtime.prepare_qmp(self.directory)
        self.assertEqual(runtime.qmp_socket_path(self.directory), first)

    def test_preexisting_files_and_dangling_symlinks_are_never_replaced(self):
        for name in ("qmp.sock", "qemu.pid", "tab.ready"):
            for symlink in (False, True):
                with self.subTest(name=name, symlink=symlink):
                    path = self.directory / name
                    if symlink:
                        path.symlink_to(self.root / "missing")
                    else:
                        path.write_bytes(b"keep")
                    with self.assertRaisesRegex(RuntimeError, "fresh"):
                        runtime.prepare_qmp(self.directory)
                    if symlink:
                        self.assertEqual(path.readlink(), self.root / "missing")
                    else:
                        self.assertEqual(path.read_bytes(), b"keep")
                    path.unlink()

    def test_unowned_or_nonprivate_vm_directory_refuses(self):
        self.directory.chmod(0o755)
        with self.assertRaisesRegex(RuntimeError, "mode-0700"):
            runtime.prepare_qmp(self.directory)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_cleanup_never_unlinks_live_or_stale_sockets_or_unrelated_files(self):
        endpoint = self.prepare()
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(str(endpoint))
            listener.listen(1)
            self.assertFalse(runtime.cleanup_empty_runtime(self.directory))
        self.assertFalse(runtime.cleanup_empty_runtime(self.directory))
        endpoint.unlink()
        sentinel = endpoint.parent / "keep"
        sentinel.write_bytes(b"keep")
        self.assertFalse(runtime.cleanup_empty_runtime(self.directory))
        self.assertEqual(sentinel.read_bytes(), b"keep")
        sentinel.unlink()
        self.assertTrue(runtime.cleanup_empty_runtime(self.directory))
        self.assertFalse(endpoint.parent.exists())
        self.assertFalse(os.path.lexists(self.directory / "qmp.sock"))

    def test_discovery_and_cleanup_refuse_redirected_runtime(self):
        link = self.directory / "qmp.sock"
        link.symlink_to(self.root / "qmp.sock")
        for function in (runtime.qmp_socket_path, runtime.cleanup_empty_runtime):
            with self.assertRaises(ValueError):
                function(self.directory)
        self.assertTrue(self.root.is_dir())
        self.assertTrue(link.is_symlink())

    def test_legacy_socket_discovery_and_cleanup(self):
        endpoint = self.directory / "qmp.sock"
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(str(endpoint))
            self.assertEqual(runtime.qmp_socket_path(self.directory), endpoint)
            self.assertFalse(runtime.cleanup_empty_runtime(self.directory))
        self.assertTrue(endpoint.exists())

    @staticmethod
    def config():
        from types import SimpleNamespace
        return SimpleNamespace(name="runtime-test", ram_mb=16, cpus=1,
                               ssh_port=32222, gui=False, external_window=False,
                               firmware="bios")

    def test_synchronous_refusal_cleans_empty_runtime_but_interrupt_retains_it(self):
        for error in (FileNotFoundError("missing QEMU"),
                      subprocess.CalledProcessError(1, ["qemu"])):
            with self.subTest(error=error), patch.object(vm, "run", side_effect=error):
                with self.assertRaises(type(error)):
                    vm.qemu_start(self.config(), self.root / "installer.iso", self.directory)
            self.assertFalse(os.path.lexists(self.directory / "qmp.sock"))
        with patch.object(vm, "run", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                vm.qemu_start(self.config(), self.root / "installer.iso", self.directory)
        self.assertTrue((self.directory / "qmp.sock").is_symlink())
        self.assertTrue(runtime.cleanup_empty_runtime(self.directory))

    def test_synchronous_failure_does_not_unlink_a_socket_left_by_qemu(self):
        def fail_after_binding(argv):
            endpoint = runtime.qmp_socket_path(self.directory)
            with socket.socket(socket.AF_UNIX) as listener:
                listener.bind(str(endpoint))
            raise subprocess.CalledProcessError(1, argv)
        with patch.object(vm, "run", side_effect=fail_after_binding):
            with self.assertRaises(subprocess.CalledProcessError):
                vm.qemu_start(self.config(), self.root / "installer.iso", self.directory)
        endpoint = runtime.qmp_socket_path(self.directory)
        self.assertTrue(endpoint.exists())
        endpoint.unlink()
        self.assertTrue(runtime.cleanup_empty_runtime(self.directory))


@unittest.skipUnless(shutil.which("qemu-system-x86_64"), "QEMU is not installed")
class RealQmpLifetimeTests(unittest.TestCase):
    setUp = QmpRuntimeTests.setUp

    def test_daemon_survives_builder_exit_and_accepts_reconnects(self):
        directory = self.root / ("é" * 60) / "vm"
        directory.mkdir(mode=0o700, parents=True)
        original = subprocess.run([
            "qemu-system-x86_64", "-machine", "none,accel=tcg", "-m", "16",
            "-S", "-nodefaults", "-display", "none",
            "-qmp", f"unix:{directory / 'qmp.sock'},server=on,wait=off",
            "-daemonize",
        ], capture_output=True, text=True, timeout=15)
        self.assertNotEqual(original.returncode, 0)
        self.assertIn("too long", original.stderr)
        # Launch an idle, diskless TCG process. No guest boots, host port, KVM,
        # display, production image or existing VM is involved.
        script = r'''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import qemu_runtime
import subprocess
directory = Path(sys.argv[2])
endpoint = qemu_runtime.prepare_qmp(directory)
subprocess.run(["qemu-system-x86_64", "-machine", "none,accel=tcg",
                "-m", "16", "-S", "-nodefaults", "-display", "none",
                "-qmp", f"unix:{endpoint},server=on,wait=off",
                "-pidfile", str(directory / "qemu.pid"), "-daemonize"], check=True)
'''
        subprocess.run([sys.executable, "-c", script, str(BUILD), str(directory)],
                       check=True, timeout=15)
        endpoint = runtime.qmp_socket_path(directory)
        try:
            for _ in range(2):
                with socket.socket(socket.AF_UNIX) as client:
                    client.settimeout(3)
                    client.connect(str(endpoint))
                    with client.makefile("rwb", buffering=0) as stream:
                        self.assertIn("QMP", json.loads(stream.readline()))
                        stream.write(b'{"execute":"qmp_capabilities"}\n')
                        self.assertIn("return", json.loads(stream.readline()))
                        stream.write(b'{"execute":"query-status"}\n')
                        self.assertIn("return", json.loads(stream.readline()))
        finally:
            # Address only the fresh private endpoint created by this test.
            with socket.socket(socket.AF_UNIX) as client:
                client.settimeout(3)
                client.connect(str(endpoint))
                with client.makefile("rwb", buffering=0) as stream:
                    stream.readline()
                    stream.write(b'{"execute":"qmp_capabilities"}\n')
                    stream.readline()
                    stream.write(b'{"execute":"quit"}\n')
                    try:
                        while stream.readline():
                            pass
                    except ConnectionResetError:
                        pass  # QEMU may reset the channel while exiting.
            import time
            deadline = time.monotonic() + 3
            while endpoint.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertFalse(endpoint.exists(), "QEMU should unlink its own socket on exit")
            self.assertTrue(runtime.cleanup_empty_runtime(directory))


if __name__ == "__main__":
    unittest.main()
