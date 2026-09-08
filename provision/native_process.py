"""Bounded command ownership for the dedicated native package helper process.

Enable subreaping only in that dedicated CLI, never at import. It owns no
background threads or unrelated launches. A subprocess return code alone is
not proof that its descendants and output pipes are finished.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time

ENVIRONMENT = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/root',
               'LANG': 'C', 'LC_ALL': 'C', 'DEBIAN_FRONTEND': 'noninteractive',
               'DPKG_FRONTEND_LOCKED': '1', 'DPKG_COLORS': 'never', 'DPKG_PAGER': ''}


class CommandFailed(RuntimeError):
    pass


def enable_subreaper():
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), 'cannot enable package-helper subreaping')


def children():
    return {int(value) for value in Path(f'/proc/self/task/{os.getpid()}/children').read_text().split()}


class Runner:
    def __init__(self, seconds=180):
        self.deadline = time.monotonic() + seconds
        self.canceled = False

    def cancel(self, *_):
        self.canceled = True

    def check(self):
        if self.canceled:
            raise CommandFailed('native package operation canceled')
        if time.monotonic() >= self.deadline:
            raise CommandFailed('native package operation deadline expired')

    def run(self, argv, *, guard=lambda: None, accepted=(0,)):
        self.check()
        guard()
        before = children()
        process = None
        poller = None
        failure = None
        try:
            poller = selectors.DefaultSelector()
            output = [bytearray(), bytearray()]
            self.check()
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, close_fds=True, start_new_session=True, env=ENVIRONMENT)
            for index, stream in enumerate((process.stdout, process.stderr)):
                os.set_blocking(stream.fileno(), False)
                poller.register(stream, selectors.EVENT_READ, index)
            while True:
                self.check()
                guard()
                for key, _ in poller.select(min(0.025, max(0, self.deadline - time.monotonic()))):
                    data = os.read(key.fd, 64 * 1024)
                    if data:
                        output[key.data].extend(data)
                        if sum(map(len, output)) > 1024 * 1024:
                            raise CommandFailed('native command output exceeds bound')
                    else:
                        poller.unregister(key.fileobj)
                code = process.poll()
                if code is not None:
                    remaining = children() - before
                    for pid in remaining:
                        os.waitpid(pid, os.WNOHANG)
                    remaining = children() - before
                    if remaining:
                        raise CommandFailed('native command left an owned descendant')
                    if not poller.get_map():
                        break
            self.check()
            guard()
            if code not in accepted:
                raise CommandFailed(f'native command exited {code}: ' +
                                    output[1].decode('utf-8', errors='replace')[-4096:])
            return code, bytes(output[0]), bytes(output[1])
        except BaseException as error:
            failure = error
            raise
        finally:
            try:
                # Popen can raise after fork but before returning its handle.
                # Ownership starts at the baseline, not at handle assignment.
                # This dedicated, single-launch subreaper owns every new child;
                # killing a parent makes escaped descendants observable here.
                cleanup_deadline = time.monotonic() + 5
                while True:
                    if process is not None and process.poll() is None:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    main = {process.pid} if process is not None else set()
                    for pid in children() - before - main:
                        waited, _ = os.waitpid(pid, os.WNOHANG)
                        if not waited:
                            try:
                                os.kill(pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                    if process is not None:
                        process.poll()
                    if (process is None or process.returncode is not None) and not children() - before:
                        break
                    if time.monotonic() >= cleanup_deadline:
                        raise CommandFailed('owned package cleanup incomplete; retain recovery state') from failure
                    time.sleep(0.01)
            finally:
                if poller is not None:
                    poller.close()
                if process is not None:
                    for stream in (process.stdout, process.stderr):
                        if stream is not None:
                            stream.close()
