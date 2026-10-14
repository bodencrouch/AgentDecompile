"""Durable job receipts and recovery of older workflow/batch observations."""
from __future__ import annotations
import json
import os
import re
import socket
import threading
import time
from pathlib import Path
from ..common import live_root

_CACHE: dict[str, tuple[tuple[int, int], list[dict]]] = {}
_LOCK = threading.Lock()
_ID = re.compile(r'^[a-f0-9]{12,32}$')
# The workbench asks for a compact activity snapshot frequently.  Rebuilding an
# index of every retained workflow receipt for each individual job lookup made
# a busy project appear disconnected even though its coordinator was running.
# Reuse the aggregate index across ordinary workbench polls. Same-process
# writes invalidate it synchronously, while receipts written by another
# process become visible on the next bounded refresh.
_RECORDS_CACHE: tuple[float, dict[str, dict]] | None = None
_RECORDS_TTL_SECONDS = 5.0

def directory() -> Path | None:
    root = live_root()
    return root / 'workbench-jobs' if root else None

def owner() -> dict:
    from ..preparation import _process_start
    return {'ownerPid': os.getpid(), 'ownerHost': socket.gethostname(), 'ownerStart': _process_start(os.getpid())}

def write(payload: dict) -> None:
    # A queued/in-flight flush belongs to its captured execution scope, never
    # to whichever database the UI happens to have selected when it finishes.
    captured = payload.get('executionRoot')
    if not isinstance(captured, str) or not Path(captured).is_absolute():
        raise OSError('Job persistence requires a captured absolute executionRoot')
    if not _ID.fullmatch(str(payload.get('id') or '')):
        raise OSError('Job persistence requires a valid job identity')
    root = Path(captured) / 'workbench-jobs'
    if root is None:
        return
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = root / (payload['id'] + '.json')
    temporary = target.with_suffix(f'.{os.getpid()}.{threading.get_ident()}.tmp')
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w', encoding='utf-8') as handle:
        handle.write(json.dumps(payload, default=str))
    temporary.replace(target)
    # Keep the aggregate view promptly consistent with receipts written by
    # this process. records() uses the same lock while reading and replacing
    # its snapshot, so no stale snapshot can survive this write's completion.
    global _RECORDS_CACHE
    with _LOCK:
        _CACHE.pop(str(target), None)
        _RECORDS_CACHE = None

def cancel_requested(job_id: str) -> bool:
    root = directory()
    return bool(root and (root / (job_id + '.cancel')).is_file())

def request_cancel(job_id: str) -> None:
    root = directory()
    if root is not None and _ID.fullmatch(job_id):
        root.mkdir(parents=True, exist_ok=True)
        (root / (job_id + '.cancel')).touch()

def _legacy(path: Path, data: dict) -> list[dict]:
    output = []
    if path.parent.name == 'preparations' and _ID.fullmatch(str(data.get('jobId') or '')):
        snapshot = {key: value for key, value in data.items() if key not in {'actions', 'jobTimingContexts', 'comparisonInputs'}}
        output.append({'id': data['jobId'], 'actionId': 'workbench.prepare', 'title': 'Prepare project', 'argv': [],
                       'params': {key: data.get(key, '') for key in ('locator', 'program', 'slug')},
                       'status': data.get('status', 'unknown'), 'createdAt': data.get('createdAt', 0),
                       'updatedAt': data.get('updatedAt'),
                       'startedAt': data.get('startedAt'), 'finishedAt': data.get('finishedAt'), 'error': data.get('error') or '',
                       'log': json.dumps(snapshot, indent=2, default=str), 'logState': 'partial', 'logTruncated': True,
                       'logReason': 'Recovered workflow state. Child operations have separate retained job output; the original coordinator console is unavailable.',
                       'historySource': str(path), **{key: data.get(key) for key in ('ownerPid', 'ownerHost', 'ownerStart')}})
    entries = list((data.get('actions') or {}).values()) if path.parent.name == 'preparations' else data.get('results', [])
    for entry in entries:
        result = entry.get('result') or {}
        job_id = entry.get('jobId') or result.get('jobId') or result.get('id')
        if not isinstance(job_id, str) or not _ID.fullmatch(job_id):
            continue
        status = result.get('status') or entry.get('status') or 'unknown'
        if 'ok' in result:
            status = 'ok' if result['ok'] else 'failed'
        text = result.get('log') or ''
        if result.get('data') is not None:
            text = json.dumps(result['data'], indent=2, default=str) + ('\n\nRecorded console tail:\n' + text if text else '')
        error = str(result.get('error') or entry.get('error') or '')
        if not error and status == 'failed':
            error = next((line.strip() for line in reversed(text.splitlines()) if line.strip().lower().startswith(('error:', 'exception:', 'failed:'))), '')
        if error and error not in text:
            text += '\n' + error
        params = {**(entry.get('context') or {}), **(entry.get('params') or {})}
        params.setdefault('locator', data.get('locator', ''))
        timing = (data.get('jobTimingContexts') or {}).get(job_id, {})
        output.append({'id': job_id, 'actionId': entry.get('action') or data.get('action') or '',
                       'title': result.get('title') or entry.get('action') or data.get('action') or 'Recorded job', 'argv': result.get('argv') or [],
                       'params': params, 'status': status, 'createdAt': result.get('createdAt') or timing.get('createdAt') or entry.get('at') or data.get('createdAt') or 0,
                       'startedAt': result.get('startedAt') or timing.get('startedAt'), 'finishedAt': result.get('finishedAt') or timing.get('finishedAt'),
                       'returncode': result.get('returncode'), 'error': error, 'log': text,
                       'logState': 'partial' if text else 'unavailable', 'logTruncated': bool(text),
                       'logReason': 'Recovered from a durable workflow/batch receipt. Original console output may have been truncated before it was saved.' if text else 'This legacy receipt retained the job identity and parameters, but no console output.',
                       'historySource': str(path), **{key: data.get(key) for key in ('ownerPid','ownerHost','ownerStart')}})
    return output

def _execution_owner_alive(owner: object) -> bool | None:
    """Return exact local child identity liveness; None means unknown/legacy."""
    if not isinstance(owner, dict) or owner.get('identity_unavailable'):
        return None
    pid = owner.get('pid')
    start_ticks = owner.get('start_ticks')
    boot_id = owner.get('boot_id')
    if type(pid) is not int or pid <= 0 or not isinstance(start_ticks, str) or not boot_id:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return None
    try:
        from ...supervision import process_identity
        current = process_identity(pid)
    except (OSError, ValueError, TypeError):
        return None
    if current.get('identity_unavailable'):
        return None
    return current.get('start_ticks') == start_ticks and current.get('boot_id') == boot_id

def _project_active_job(data: dict) -> dict:
    """Project stale state without treating server death as child death."""
    result = dict(data)
    if result.get('status') not in {'queued', 'running', 'cancelling'}:
        return result
    from ..preparation import _owner_alive
    owner_alive = _owner_alive(result)
    if not owner_alive and _execution_owner_alive(result.get('executionOwner')) is not False:
        # A dead dashboard process does not prove its separately supervised
        # child has stopped. Unknown identity is retained.
        owner_alive = True
    if not owner_alive:
        result['status'] = 'interrupted'
        result['finishedAt'] = result.get('finishedAt') or time.time()
        result['error'] = result.get('error') or (
            'The owning process and its recorded execution child stopped '
            'before recording completion; retained output is available for reconciliation.'
        )
    return result

def _job_receipt(path: Path) -> dict | None:
    """Read and project one durable job without rebuilding the history index."""
    try:
        if path.is_symlink() or not path.is_file():
            return None
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not _ID.fullmatch(str(data.get('id') or '')):
            return None
        return _project_active_job(data)
    except (OSError, ValueError, TypeError):
        return None

def records() -> dict[str, dict]:
    global _RECORDS_CACHE
    root = live_root()
    if root is None:
        return {}
    now = time.monotonic()
    result: dict[str, dict] = {}
    with _LOCK:
        root_key = str(root.resolve())
        if (_RECORDS_CACHE is not None and getattr(records, '_cache_root', None) == root_key
                and now - _RECORDS_CACHE[0] < _RECORDS_TTL_SECONDS):
            return dict(_RECORDS_CACHE[1])
        paths = [p for folder in ('preparations', 'workbench-batches', 'workbench-jobs') for p in (root / folder).glob('*.json') if not p.is_symlink()]
        for path in paths:
            try:
                stat = path.stat(); signature = (stat.st_mtime_ns, stat.st_size)
                cached = _CACHE.get(str(path))
                if cached is None or cached[0] != signature:
                    data = json.loads(path.read_text(encoding='utf-8'))
                    # Cache the durable source, not a time-sensitive owner
                    # liveness projection. That projection is recomputed below.
                    rows = [data] if path.parent.name == 'workbench-jobs' else _legacy(path, data)
                    _CACHE[str(path)] = (signature, rows)
                else:
                    rows = cached[1]
                if path.parent.name == 'workbench-jobs':
                    rows = [_project_active_job(row) for row in rows]
                for row in rows:
                    if not _ID.fullmatch(str(row.get('id') or '')):
                        continue
                    previous = result.get(row['id'])
                    def observed(value: dict) -> float:
                        return max(float(value.get(key) or 0) for key in ('finishedAt', 'updatedAt', 'capturedAt', 'createdAt'))
                    if previous is None or observed(row) > observed(previous) or (observed(row) == observed(previous) and path.parent.name == 'workbench-jobs'):
                        result[row['id']] = row
            except (OSError, ValueError, TypeError):
                continue
        _RECORDS_CACHE = (now, result)
        records._cache_root = root_key
    return dict(result)

def historical(job_id: str) -> dict | None:
    if not _ID.fullmatch(job_id):
        return None
    root = directory()
    if root is not None:
        # JobStore receipts are the canonical source for individual job
        # requests. Legacy preparations/batches are consulted only if absent.
        direct = _job_receipt(root / (job_id + '.json'))
        if direct is not None and direct.get('id') == job_id:
            return direct
    return records().get(job_id)
