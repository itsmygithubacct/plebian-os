"""Bounded, identity-keyed ownership facts for the measurement harness.

The tracker never signals or reaps. Facts can be supplied directly by pure
tests; only snapshot() reads /proc. A remembered child remains owned after its
parent exits. A new process at the same numeric PID does not inherit ownership.
"""
from __future__ import annotations

import errno
import os
import time

MAX_OWNED = 1024
MAX_ERRORS = 64
# A task in EXIT_DEAD ('X') whose signal struct is already released is printed
# by the kernel with ppid 0 and pgid/sid -1 until release_task unhashes its PID
# (microseconds). That row is neither a live identity nor proof of absence:
# re-read, bounded, until /proc reports the PID gone (ENOENT/ESRCH) or shows a
# full row (a later process at that PID carries a different start).
EXIT_DEAD_REREADS = 100
EXIT_DEAD_PAUSE = 0.001


def read_stat(pid):
    """Read an identity; distinguish actual disappearance from unreadability."""
    if type(pid) is not int or pid <= 0:
        raise ValueError('PID must be a positive integer')
    for attempt in range(EXIT_DEAD_REREADS + 1):
        try:
            with open(f'/proc/{pid}/stat', 'rb') as handle:
                data = handle.read(8193)
        except OSError as error:
            if error.errno in (errno.ENOENT, errno.ESRCH):
                return None
            raise
        close = data.rfind(b')')
        fields = data[close + 2:].split() if close >= 0 else []
        if len(data) > 8192 or len(fields) < 20:
            raise ValueError(f'invalid process stat for {pid}')
        try:
            if int(data[:data.find(b' ')]) != pid:
                raise ValueError('stat PID mismatch')
            result = {'state': fields[0].decode('ascii'), 'ppid': int(fields[1]),
                      'pgid': int(fields[2]), 'start': int(fields[19])}
            try:
                validate(result)
            except ValueError:
                if result['state'] == 'X' and attempt < EXIT_DEAD_REREADS:
                    time.sleep(EXIT_DEAD_PAUSE)
                    continue
                raise
            return result
        except (UnicodeError, IndexError, ValueError) as error:
            raise ValueError(f'invalid process stat for {pid}') from error


def validate(row):
    for name in ('ppid', 'pgid', 'start'):
        if type(row.get(name)) is not int or row[name] < 0:
            raise ValueError(f'invalid process {name}')
    if not isinstance(row.get('state'), str) or len(row['state']) != 1:
        raise ValueError('invalid process state')


def snapshot():
    """Return per-PID facts/errors, never translate permission errors to absence."""
    rows, errors = {}, {}
    for entry in os.listdir('/proc'):
        if not entry.isascii() or not entry.isdigit():
            continue
        pid = int(entry)
        try:
            row = read_stat(pid)
        except (OSError, ValueError) as error:
            errors[pid] = f'{type(error).__name__}: {error}'
        else:
            if row is not None:
                rows[pid] = row
    return rows, errors


class OwnedTree:
    def __init__(self, pid, row, *, maximum=MAX_OWNED):
        if type(pid) is not int or pid <= 0:
            raise ValueError('invalid leader PID')
        if type(maximum) is not int or maximum < 1 or maximum > MAX_OWNED:
            raise ValueError('invalid owned identity bound')
        validate(row)
        self.leader = (pid, row['start'])
        self.maximum = maximum
        self.known = {self.leader: {'pid': pid, **row,
                                   'parent_identity': None}}
        self.errors = []
        self.error_count = 0
        self.current = {pid: dict(row)}
        self.observation_complete = False

    def error(self, message):
        self.error_count += 1
        if len(self.errors) < MAX_ERRORS:
            self.errors.append(str(message)[:1024])

    def observe(self, rows, errors=None):
        """Admit descendants of matching known identities in this observation.

        Parent/start edges are the snapshot's observation, not atomic kernel
        lineage proof. Signal delivery must separately recheck the identity
        after opening a pidfd. Errors for known PIDs latch incomplete coverage.
        """
        self.observation_complete = False
        errors_before = self.error_count
        errors = errors or {}
        current = {}
        for (pid, start), _record in self.known.items():
            if pid in errors:
                self.error(f'known PID {pid}/{start}: {errors[pid]}')
            row = rows.get(pid)
            if row is not None:
                validate(row)
                if row['start'] == start:
                    current[pid] = dict(row)
        changed = True
        while changed:
            changed = False
            for pid, row in rows.items():
                if pid in current or row['ppid'] not in current:
                    continue
                validate(row)
                parent = current[row['ppid']]
                if row['start'] < parent['start']:
                    self.error(f'inconsistent parent age for PID {pid}')
                    continue
                identity = (pid, row['start'])
                if identity not in self.known:
                    if len(self.known) >= self.maximum:
                        self.error('owned identity bound exceeded')
                        self.current = current
                        return dict(current)
                    self.known[identity] = {
                        'pid': pid, **row,
                        'parent_identity': [row['ppid'], parent['start']]}
                current[pid] = dict(row)
                changed = True
        self.current = current
        self.observation_complete = self.error_count == errors_before
        return dict(current)

    def refresh(self):
        self.observation_complete = False
        try:
            rows, errors = snapshot()
            return self.observe(rows, errors)
        except (OSError, ValueError) as error:
            self.error(f'process snapshot failed: {type(error).__name__}: {error}')
            # Last observed live rows are not proof of current absence. Keep
            # them for reporting; callers still revalidate before any action.
            return dict(self.current)

    def records(self):
        return [dict(row) for _identity, row in sorted(self.known.items())]

    def same_identity(self, pid, row):
        return row is not None and (pid, row['start']) in self.known

    def adopted_zombies(self, observer_pid):
        return [(pid, row['start']) for pid, row in sorted(self.current.items())
                if (pid, row['start']) != self.leader
                and row['ppid'] == observer_pid and row['state'] == 'Z']
