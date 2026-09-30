"""Durable wake cursors and job-store restore reconciliation (U9 FP-25; design section 4).

Wake registration: a blocked transition stores its wait basis and the event-log cursor it
last saw. ``Waits.check`` replays every event after that cursor and rechecks the predicate
before sleeping, so an event landing between a check and a subscribe cannot be lost.
Delivery is at least once; ``WakeLog.append`` and ``ActionOnce.claim`` are idempotent by key,
so a replayed event never causes a second dispatch or acceptance.

Restore: after the job-receipt store is restored from a backup, late receipts from workers
that kept running are merged by ``receiptVersion``. Older or equal versions are ignored; a
version jump is recorded as a lost-event window rather than assumed complete. Attempt
counts and generations never go down. A job restored as active with no late receipt and no
live owner becomes ``unknownOutcome``: it is not relaunched until reconciled, and other
jobs continue.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

ACTIVE = frozenset({'queued', 'running', 'cancelling', 'interrupted', 'submitting'})


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.tmp-')
    with os.fdopen(fd, 'w') as handle:
        json.dump(value, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class WakeLog:
    """Append-only event outbox with a monotonically increasing sequence."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        (self.root / 'events').mkdir(parents=True, exist_ok=True)
        (self.root / 'keys').mkdir(parents=True, exist_ok=True)

    def head(self) -> int:
        return max((int(p.stem) for p in (self.root / 'events').glob('*.json')), default=0)

    def append(self, event_key: str, kind: str, body: Mapping[str, Any] | None = None) -> tuple[int, bool]:
        """Return ``(sequence, new)``; a redelivered key returns its original sequence."""
        marker = self.root / 'keys' / (_key(event_key) + '.json')
        if marker.exists():
            return json.loads(marker.read_text())['sequence'], False
        record = {'eventKey': event_key, 'kind': kind, 'body': dict(body or {})}
        with open(self.root / '.append.lock', 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)  # one sequence per event, even across processes
            if marker.exists():  # a concurrent redelivery won the race
                return json.loads(marker.read_text())['sequence'], False
            sequence = self.head() + 1
            _save(self.root / 'events' / f'{sequence:012d}.json', {'sequence': sequence, **record})
            _save(marker, {'sequence': sequence})
        return sequence, True

    def after(self, cursor: int) -> list[dict]:
        return [json.loads(p.read_text()) for p in sorted((self.root / 'events').glob('*.json'))
                if int(p.stem) > cursor]


class Waits:
    """Durable wait registrations: basis plus the cursor recorded with the blocked transition."""

    def __init__(self, root: Path | str, log: WakeLog) -> None:
        self.root, self.log = Path(root), log

    def register(self, wait_id: str, basis: Mapping[str, Any]) -> dict:
        row = {'waitId': wait_id, 'basis': dict(basis), 'cursor': self.log.head()}
        _save(self.root / (_key(wait_id) + '.json'), row)
        return row

    def get(self, wait_id: str) -> dict | None:
        path = self.root / (_key(wait_id) + '.json')
        return json.loads(path.read_text()) if path.exists() else None

    def check(self, wait_id: str, predicate: Callable[[list[dict]], bool]) -> dict:
        """Replay events after the stored cursor, then decide; the cursor advances durably."""
        row = self.get(wait_id)
        if row is None:
            raise KeyError(wait_id)
        events = self.log.after(row['cursor'])
        wake = bool(predicate(events))
        if events:
            row['cursor'] = events[-1]['sequence']
            _save(self.root / (_key(wait_id) + '.json'), row)
        return {'wake': wake, 'cursor': row['cursor'], 'replayed': len(events)}


class ActionOnce:
    """Idempotent reducer guard: each dispatch/acceptance key is claimed at most once."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def claim(self, action_key: str) -> bool:
        try:
            fd = os.open(self.root / _key(action_key), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return False
        os.close(fd)
        return True


def _version(row: Mapping[str, Any]) -> int:
    value = row.get('receiptVersion')
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def reconcile_after_restore(
    restored: Mapping[str, Mapping[str, Any]], late: Iterable[Mapping[str, Any]], *,
    live_owner: Callable[[Mapping[str, Any]], bool] = lambda row: False,
) -> tuple[dict[str, dict], dict]:
    """Merge late receipts into a restored store; return ``(receipts, report)``."""
    merged = {job_id: dict(row) for job_id, row in restored.items()}
    report: dict[str, list] = {'accepted': [], 'ignoredStaleOrDuplicate': [], 'lostEventWindows': [],
                               'unknownOutcome': [], 'liveOwnerKept': []}
    seen_late: set[str] = set()
    for row in sorted(late, key=lambda r: (str(r.get('id')), _version(r))):
        job_id = str(row.get('id'))
        current = merged.get(job_id)
        have = _version(current) if current else 0
        if current is not None and _version(row) <= have:
            report['ignoredStaleOrDuplicate'].append({'id': job_id, 'receiptVersion': _version(row)})
            continue
        if _version(row) > have + 1:
            report['lostEventWindows'].append({'id': job_id, 'missingVersions': [have + 1, _version(row) - 1]})
        new = dict(row)
        if current is not None:  # limits and generations never go down
            new['executionAttempt'] = max(current.get('executionAttempt') or 0, row.get('executionAttempt') or 0)
        merged[job_id] = new
        seen_late.add(job_id)  # only an accepted receipt says anything about the job now
        report['accepted'].append({'id': job_id, 'receiptVersion': _version(row)})
    for job_id, row in merged.items():
        if job_id in seen_late or row.get('status') not in ACTIVE:
            continue
        if live_owner(row):
            report['liveOwnerKept'].append(job_id)
            continue
        row.update(unknownOutcome=True, ownershipUnresolved=True,
                   nextAction='reconcile_before_continuing',
                   restoreNote='Restored as active with no later receipt and no live owner; not relaunched.')
        report['unknownOutcome'].append(job_id)
    return merged, report
