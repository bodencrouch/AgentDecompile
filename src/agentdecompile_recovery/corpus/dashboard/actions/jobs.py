"""In-process job runner for cataloged dashboard actions."""

from __future__ import annotations

import json
import os
import re
import queue
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from agentdecompile_recovery.languages import SourceLanguage, default_source_language, language_spec

from agentdecompile_recovery.corpus.dashboard.actions.catalog import (
    ActionSpec,
    action_by_id,
    apply_defaults,
    build_command,
    validate_params,
)
from agentdecompile_recovery.corpus.dashboard.common import live_db, live_root

from agentdecompile_recovery.corpus.dashboard.mcp_bridge import CONTEXT_LOCK

MAX_JOBS = 50
MAX_CONCURRENT = 4
MAX_LOG_BYTES = 2 * 1024 * 1024
POLL_S = 0.25
# One MCP session owns one mutable current-project/current-program context.
# Serialize complete dashboard sequences without holding the bridge's loopback
# lock across the HTTP request (which can deadlock the in-process handler).
MCP_EXECUTOR_LOCK = threading.Lock()
_PREPARATION_FACTS_INVENTORY = object()
_PREPARATION_PROBE = object()

_DASHBOARD_AUTO_CHECKIN_TOOLS = frozenset(
    {
        "managesymbols",
        "managefunction",
        "managecomments",
        "managestructures",
        "manageenums",
        "managedatatypes",
        "applydatatype",
        "managebookmarks",
        "managefunctiontags",
        "managestrings",
        "matchfunction",
    }
)


def _auto_checkin_enabled() -> bool:
    for var_name in ("AGENTDECOMPILE_AUTO_CHECKIN", "AGENT_DECOMPILE_AUTO_CHECKIN"):
        value = os.getenv(var_name)
        if value and value.strip().lower() in {"1", "true", "yes", "on"}:
            return True
    return False


def _tool_key(name: str) -> str:
    return re.sub(r"[^a-z]", "", (name or "").lower())

IDENTITY_WRITERS = frozenset({
    "corpus.logical-build",
    "workbench.merge-evidence",
    "corpus.propagate-corpus",
    "corpus.bind-identities",
    "corpus.merge-parts",
    "corpus.apply-stabs",
    "corpus.propagate-source",
})
GHIDRA_MUTATE = frozenset({
    "corpus.apply-annotations",
})

Executor = Callable[[list[str], Path, threading.Event], tuple[int, str]]


def _json_safe(value: Any) -> Any:
    """Return an API/persistence-safe copy of action parameters.

    Action defaults retain useful typed values such as ``Path`` for command
    construction.  Job records cross an HTTP and JSON receipt boundary, where
    those values must be represented by their stable string form.
    """
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return [_json_safe(item) for item in sorted(value, key=str)]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


@dataclass
class JobRecord:
    id: str
    action_id: str
    title: str
    argv: list[str]
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    returncode: int | None = None
    error: str = ""
    log: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    history_only: bool = False
    owner_unavailable: bool = False
    history_source: str = ''
    log_state: str = 'available'
    log_reason: str = ''
    log_truncated: bool = False
    work_progress: dict[str, Any] | None = None
    trusted_preparation_facts_inventory: bool = False
    trusted_preparation_probe: bool = False

    def to_dict(self, *, include_log: bool = True, include_details: bool = True) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "actionId": self.action_id,
            "title": self.title,
            "argv": list(self.argv) if include_log else [],
            "status": self.status,
            "createdAt": self.created_at,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "returncode": self.returncode,
            "error": self.error,
            "params": _json_safe(dict(self.params) if include_details else {
                key: value for key, value in self.params.items()
                if key not in {"candidateSource", "code", "script", "source"}
            }),
            "historyOnly": self.history_only,
            "ownerUnavailable": self.owner_unavailable,
            "historySource": self.history_source,
            "logState": self.log_state if self.log or self.history_only else ('pending' if self.status in {'queued', 'running', 'cancelling'} else 'empty'),
            "logReason": self.log_reason,
            "logTruncated": self.log_truncated or len(self.log) >= MAX_LOG_BYTES,
        }
        if self.work_progress is not None:
            payload["workProgress"] = _json_safe(dict(self.work_progress))
        if include_log:
            payload["log"] = self.log
            payload["progress"] = infer_job_progress(self.status, self.log, self.work_progress)
        else:
            # The dock polls a large job index frequently.  Scanning every
            # historical log for percent-like text makes that read endpoint
            # monopolize the interpreter while recovery is running.  Exact
            # log-derived progress is loaded only when an operator expands a
            # job; the index still truthfully identifies queued and finished
            # jobs without pretending a running job has a measured percent.
            payload["progress"] = infer_job_progress(self.status, "", self.work_progress)
        return payload


_PERCENT_RE = re.compile(r"(?<!\d)(\d{1,3})\s*%")


def infer_job_progress(status: str, log: str = "", work_progress: dict[str, Any] | None = None) -> int | None:
    """Return observed log progress; fall back to Ghidra percent lines and status hints."""
    records = [work_progress] if isinstance(work_progress, dict) else []
    for line in reversed(log.splitlines()):
        try:
            record = json.loads(line)
        except (ValueError, TypeError):
            continue
        records.append(record)
    for record in records:
        if not isinstance(record, dict) or record.get("event") not in {"progress", "match-pair-progress"}:
            continue
        done, total = record.get("completed"), record.get("total")
        if isinstance(done, (int, float)) and isinstance(total, (int, float)) and total > 0 and 0 <= done <= total:
            return int(100 * done / total)
    percent = _last_percent(log)
    if percent is not None:
        return percent
    if status == "ok":
        return 100
    if status == "queued":
        return 4
    return None


def _latest_work_progress(log: str) -> dict[str, Any] | None:
    for line in reversed(log.splitlines()):
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict) or event.get("event") != "match-pair-progress":
            continue
        if isinstance(event.get("completed"), int) and isinstance(event.get("total"), int):
            return event
    return None


def _last_percent(log: str) -> int | None:
    matches = _PERCENT_RE.findall(log or "")
    if not matches:
        return None
    value = int(matches[-1])
    if 0 <= value <= 100:
        return value
    return None


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}
        self._order: list[str] = []
        self._cancels: dict[str, threading.Event] = {}
        self._running = 0
        self._identity_held: dict[str, str] = {}
        self._ghidra_held: dict[str, str] = {}
        self.executor: Executor | None = None
        self._persisted_at: dict[str, float] = {}
        self._persist_pending: dict[str, dict[str, Any]] = {}
        self._persist_lock = threading.Lock()
        self._persist_wake = threading.Event()
        threading.Thread(target=self._persist_loop, name="dashboard-job-receipts", daemon=True).start()

    def _persist_locked(self, job: JobRecord, *, force: bool = False) -> None:
        """Queue the latest receipt snapshot; never perform filesystem I/O here."""
        now = time.monotonic()
        if not force and now - self._persisted_at.get(job.id, 0) < .1:
            return
        payload = job.to_dict()
        payload['updatedAt'] = time.time()
        payload['logTruncated'] = job.log_truncated or len(job.log) >= MAX_LOG_BYTES
        self._persisted_at[job.id] = now
        with self._persist_lock:
            self._persist_pending[job.id] = payload
        self._persist_wake.set()

    def _persist_loop(self) -> None:
        from . import job_history
        while True:
            self._persist_wake.wait()
            self._persist_wake.clear()
            with self._persist_lock:
                pending, self._persist_pending = self._persist_pending, {}
            for job_id, payload in pending.items():
                try:
                    payload.update(job_history.owner())
                    job_history.write(payload)
                except OSError as exc:
                    with self._lock:
                        job = self._jobs.get(job_id)
                        if job is not None:
                            job.log_reason = f'Durable job output could not be saved: {exc}'

    def _watch_cancel(self, job_id: str, cancel: threading.Event) -> None:
        from .job_history import cancel_requested
        while not cancel.wait(.25):
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None or job.status not in {'queued', 'running', 'cancelling'}:
                    return
            if cancel_requested(job_id):
                cancel.set()
                return

    def list(self, *, compact: bool = False) -> list[JobRecord]:
        from .job_history import records
        history = {key: _from_history(value, compact=compact) for key, value in records().items()}
        with self._lock:
            history.update({key: _copy_job(job) for key, job in self._jobs.items()})
        return sorted(history.values(), key=lambda job: job.created_at, reverse=True)

    def get(self, job_id: str, *, compact: bool = False) -> JobRecord | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                return _copy_job(job)
        from .job_history import historical
        payload = historical(job_id)
        return _from_history(payload, compact=compact) if payload else None

    def start(
        self,
        action: ActionSpec,
        params: dict[str, Any],
        argv: list[str],
        *,
        trusted_preparation_facts_inventory: bool = False,
        trusted_preparation_probe: bool = False,
    ) -> JobRecord:
        job = JobRecord(
            id=uuid.uuid4().hex[:12],
            action_id=action.id,
            title=action.title,
            argv=list(argv),
            params=dict(params),
            trusted_preparation_facts_inventory=trusted_preparation_facts_inventory,
            trusted_preparation_probe=trusted_preparation_probe,
        )
        cancel = threading.Event()
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._cancels[job.id] = cancel
            self._persist_locked(job, force=True)
            self._trim_locked()
        threading.Thread(target=self._watch_cancel, args=(job.id, cancel), daemon=True).start()
        thread = threading.Thread(
            target=self._run,
            args=(job.id, cancel),
            name=f"dashboard-job-{job.id}",
            daemon=True,
        )
        thread.start()
        return self.get(job.id) or job

    def cancel(self, job_id: str) -> JobRecord | None:
        from .job_history import request_cancel
        known = self.get(job_id)
        if known is None:
            return None
        if known.history_only:
            if known.status in {'queued', 'running', 'cancelling'} and not known.owner_unavailable:
                request_cancel(job_id)
                known.status = 'cancelling'
            return known
        with self._lock:
            job = self._jobs.get(job_id)
            event = self._cancels.get(job_id)
            if job is None:
                return None
            if job.status in {"queued", "running"}:
                job.status = "cancelling"
            if event is not None:
                event.set()
            self._persist_locked(job, force=True)
            return _copy_job(job)

    def _run(self, job_id: str, cancel: threading.Event) -> None:
        identity_key = ""
        ghidra_key = ""
        action = action_by_id(self._jobs[job_id].action_id)
        while True:
            with self._lock:
                if cancel.is_set():
                    job = self._jobs[job_id]
                    job.status = "cancelled"
                    job.finished_at = time.time()
                    self._persist_locked(job, force=True)
                    return
                job = self._jobs[job_id]
                coordinator = job.action_id in {"workbench.prepare", "workbench.workflow-control", "workbench.activity-snapshot"}
                can_run = self._running < MAX_CONCURRENT
                if can_run and (job.action_id in IDENTITY_WRITERS or job.action_id == "corpus.match-pair"):
                    identity_key = (
                        match_pair_lock_key(job.params)
                        if job.action_id == "corpus.match-pair"
                        else identity_lock_key(job.params)
                    ) or ""
                    holder = self._identity_held.get(identity_key)
                    if identity_key and holder and holder != job_id:
                        can_run = False
                mutates_ghidra = job.action_id in GHIDRA_MUTATE or (action is not None and action.backend == "mcp-cli" and action.mutating)
                if can_run and mutates_ghidra:
                    ghidra_key = ghidra_lock_key(job.params)
                    holder = self._ghidra_held.get(ghidra_key)
                    if ghidra_key and holder and holder != job_id:
                        can_run = False
                if can_run:
                    # Coordinators wait on and schedule child jobs; they do
                    # not themselves consume a worker slot. Counting them
                    # here but deliberately not decrementing them in finally
                    # permanently exhausted MAX_CONCURRENT after four
                    # preparation runs, leaving every real MCP job queued.
                    if not coordinator:
                        self._running += 1
                    if identity_key:
                        self._identity_held[identity_key] = job_id
                    if ghidra_key:
                        self._ghidra_held[ghidra_key] = job_id
                    job.status = "running"
                    job.started_at = time.time()
                    self._persist_locked(job, force=True)
                    argv = list(job.argv)
                    break
            time.sleep(POLL_S)
        cwd = live_root() or Path.cwd()
        try:
            if action is not None and action.backend == "preparation":
                from agentdecompile_recovery.corpus.dashboard.preparation import execute
                code, log = execute(dict(job.params), cancel)
            elif action is not None and action.backend == "merge-evidence":
                from agentdecompile_recovery.corpus.dashboard.workflow import merge_evidence
                code, log = 0, json.dumps(merge_evidence(str(job.params["db"]), str(job.params["run"])))
            elif action is not None and action.backend == "workflow-control":
                from agentdecompile_recovery.corpus.dashboard.preparation import control
                code, log = 0, json.dumps(control(dict(job.params)))
            elif action is not None and action.backend == "activity-snapshot":
                from agentdecompile_recovery.corpus.dashboard.entity_activity import snapshot
                code, log = 0, json.dumps(snapshot(locator=job.params.get("locator", ""), slug=job.params.get("slug", ""), program=job.params.get("program", "") or job.params.get("programPath", "")))
            elif action is not None and action.backend == "matching":
                from agentdecompile_recovery.corpus.dashboard.actions.matching import execute
                code, log = execute(dict(job.params), cancel)
            elif action is not None and action.backend == "source-archive":
                def archive_progress(text: str) -> None:
                    with self._lock:
                        self._jobs[job_id].log = text[-MAX_LOG_BYTES:]
                        self._persist_locked(self._jobs[job_id], force=True)
                params = dict(job.params)
                workspace = (live_root() or Path.cwd()).resolve()
                staging_root = workspace / 'exports' / 'source-archives' / '.staging'
                staging_root.mkdir(parents=True, exist_ok=True)
                staging = Path(tempfile.mkdtemp(prefix=f'{job_id}-', dir=staging_root))
                request_path = staging / 'request.json'
                request_path.write_text(json.dumps(params, default=str), encoding='utf-8')
                try:
                    archive_timeout = float(os.environ.get('AGENT_DECOMPILE_SOURCE_ARCHIVE_TIMEOUT_SECONDS', '900'))
                except ValueError:
                    archive_timeout = 900.0
                deadline = time.monotonic() + max(1.0, archive_timeout)
                def remaining() -> float:
                    return max(0.0, deadline - time.monotonic())
                resolve_code, resolve_output = _default_executor(
                    [sys.executable, '-m', 'agentdecompile_recovery.corpus.dashboard.source_archive', '--resolve', str(request_path)],
                    workspace, cancel, on_output=archive_progress, timeout_seconds=min(remaining(), 120.0),
                )
                context: dict[str, Any] = {}
                resolve_pid: int | None = None
                for line in reversed(resolve_output.splitlines()):
                    try:
                        event = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    resolve_pid = event.get('workerPid') if isinstance(event.get('workerPid'), int) else resolve_pid
                    if event.get('event') == 'context' and isinstance(event.get('context'), dict):
                        context = event['context']
                        break
                    if event.get('event') == 'error':
                        raise ValueError(str(event.get('error') or 'Source archive binding resolution failed.'))
                if resolve_code or not context:
                    raise ValueError('Source archive binding resolution did not reach a confirmed terminal result.')
                if cancel.is_set():
                    raise InterruptedError('Source archive cancelled after binding resolution.')
                if remaining() <= 0:
                    raise TimeoutError('Source archive deadline expired during binding resolution; no archive was published.')
                generation = {'ok': False, 'requested': True, 'reason': 'No unique project/program binding is available for whole-program source generation.'}
                if context.get('locator') and context.get('program'):
                    generation = _bounded_archive_export(staging / 'program.c', context, cancel, deadline)
                    generation['requested'] = True
                if generation.get('ownershipResolved') is False:
                    result = generation
                    code, log = 124, json.dumps(result, default=str)
                    output = ''
                else:
                    if cancel.is_set():
                        raise InterruptedError('Source archive cancelled after live export.')
                    if remaining() <= 0:
                        raise TimeoutError('Source archive deadline expired after live export; no archive was published.')
                    params['_prefetchedGeneration'] = generation
                    params['_prefetchedGenerationDir'] = str(staging)
                    params['_resolveWorkerPid'] = resolve_pid
                    request_path.write_text(json.dumps(params, default=str), encoding='utf-8')
                    code, output = _default_executor(
                        [sys.executable, '-m', 'agentdecompile_recovery.corpus.dashboard.source_archive', '--worker', str(request_path)],
                        workspace, cancel, on_output=archive_progress,
                        timeout_seconds=remaining(),
                    )
                    result = {}
                    for line in reversed(output.splitlines()):
                        try:
                            event = json.loads(line)
                        except (TypeError, ValueError):
                            continue
                        if event.get('event') == 'result' and isinstance(event.get('result'), dict):
                            result = event['result']
                            break
                        if event.get('event') == 'error':
                            result = {'ok': False, 'error': str(event.get('error') or 'Source archive worker failed.')}
                            break
                    unresolved = '[process did not reach a terminal state; ownership remains unresolved]' in output
                    if unresolved:
                        result = {'ok': False, 'quarantined': True, 'ownershipResolved': False,
                                  'error': 'Source archive worker ownership is unresolved; output is quarantined and must not be published.'}
                    elif result.get('ownershipResolved') is True:
                        shutil.rmtree(staging)
                    code, log = (0 if code == 0 and result.get('ok') else code or 1), json.dumps(result, default=str)
            elif action is not None and action.backend == "mcp-cli":
                code, log = _mcp_executor(
                    action,
                    dict(job.params),
                    cancel,
                    trusted_preparation_facts_inventory=job.trusted_preparation_facts_inventory,
                    trusted_preparation_probe=job.trusted_preparation_probe,
                )
            else:
                def publish_log(text: str) -> None:
                    with self._lock:
                        self._jobs[job_id].log = text[-MAX_LOG_BYTES:]
                        progress = _latest_work_progress(text)
                        if progress is not None:
                            self._jobs[job_id].work_progress = progress
                        self._persist_locked(self._jobs[job_id], force=True)
                if self.executor:
                    code, log = self.executor(argv, cwd, cancel)
                else:
                    # Pair matching is durable and idempotent for a frozen
                    # prepare run. An Unlimited project budget therefore has
                    # no hidden child-process deadline; cancellation remains
                    # the stop mechanism. Finite project budgets keep the
                    # normal executor limit and are cancelled by preparation.
                    unlimited_match = (
                        job.action_id == "corpus.match-pair"
                        and job.params.get("_preparationUnlimited") is True
                    )
                    code, log = _default_executor(
                        argv, cwd, cancel, on_output=publish_log,
                        unlimited=unlimited_match,
                    )
                if action is not None and action.backend == "bsim-cli":
                    from agentdecompile_recovery.corpus.bsim_ops import _bsim_cli_error
                    if _bsim_cli_error(log, ""):
                        code = code or 1
            with self._lock:
                job = self._jobs[job_id]
                job.log = log[-MAX_LOG_BYTES:]
                job.returncode = code
                job.finished_at = time.time()
                if cancel.is_set() and job.status != "cancelled":
                    job.status = "cancelled"
                elif code == 0:
                    job.status = "ok"
                else:
                    job.status = "failed"
                    job.error = next((line.strip() for line in reversed(job.log.splitlines()) if line.strip().lower().startswith(('error:', 'exception:', 'failed:'))), f'Operation exited with status {code}. Inspect its retained output for details.')
        except Exception as exc:  # noqa: BLE001 — job must not kill the server
            with self._lock:
                job = self._jobs[job_id]
                job.error = str(exc)
                job.status = "failed"
                job.finished_at = time.time()
        finally:
            with self._lock:
                self._persist_locked(self._jobs[job_id], force=True)
                if not coordinator:
                    self._running = max(0, self._running - 1)
                if identity_key and self._identity_held.get(identity_key) == job_id:
                    self._identity_held.pop(identity_key, None)
                if ghidra_key and self._ghidra_held.get(ghidra_key) == job_id:
                    self._ghidra_held.pop(ghidra_key, None)

    def _trim_locked(self) -> None:
        while len(self._order) > MAX_JOBS:
            old = self._order.pop(0)
            job = self._jobs.get(old)
            if job is not None and job.status in {"queued", "running", "cancelling"}:
                self._order.insert(0, old)
                break
            self._jobs.pop(old, None)
            self._cancels.pop(old, None)


def _copy_job(job: JobRecord) -> JobRecord:
    return JobRecord(
        id=job.id,
        action_id=job.action_id,
        title=job.title,
        argv=list(job.argv),
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        returncode=job.returncode,
        error=job.error,
        log=job.log,
        params=dict(job.params),
        history_only=job.history_only, owner_unavailable=job.owner_unavailable,
        history_source=job.history_source, log_state=job.log_state,
        log_reason=job.log_reason, log_truncated=job.log_truncated,
        work_progress=dict(job.work_progress) if job.work_progress is not None else None,
        trusted_preparation_facts_inventory=job.trusted_preparation_facts_inventory,
        trusted_preparation_probe=job.trusted_preparation_probe,
    )


def _from_history(payload: dict, *, compact: bool = False) -> JobRecord:
    status = str(payload.get('status') or 'unknown')
    # A durable receipt is not an executor handle. After a server restart we
    # cannot safely prove that its former owner still represents this action
    # (PIDs may be reused), nor can the dashboard cancel it. Never present a
    # receipt-only operation as live work.
    unavailable = status in {'queued', 'running', 'cancelling'}
    error = str(payload.get('error') or '')
    if unavailable:
        status = 'interrupted'
        error = error or 'This is a retained job receipt, not a live dashboard handle. Reconcile its output before resubmitting.'
    return JobRecord(id=payload['id'], action_id=payload.get('actionId', ''), title=payload.get('title', ''),
                     argv=list(payload.get('argv') or []), status=status, created_at=payload.get('createdAt') or 0,
                     started_at=payload.get('startedAt'), finished_at=payload.get('finishedAt'), returncode=payload.get('returncode'),
                     error=error, log=payload.get('log') or '', params=dict(payload.get('params') or {}),
                     history_only=True, owner_unavailable=unavailable, history_source=payload.get('historySource') or 'durable-job-receipt',
                     log_state=payload.get('logState') or ('available' if payload.get('log') else 'unavailable'),
                     log_reason=payload.get('logReason') or '', log_truncated=bool(payload.get('logTruncated')),
                     work_progress=payload.get('workProgress') if isinstance(payload.get('workProgress'), dict) else (None if compact else _latest_work_progress(payload.get('log') or '')))


def _ghidra_export_format_for(language: SourceLanguage) -> str:
    ext = language_spec(language).default_export_extension.lower()
    if ext in {".cpp", ".cxx", ".cc", ".hpp", ".hh", ".hxx"}:
        return "cpp"
    return "c"


def _export_archive_program(output_path: Path, context: dict[str, Any], cancel: threading.Event) -> dict[str, Any]:
    export, inspect = action_by_id("mcp.export"), action_by_id("mcp.execute-script")
    if export is None or inspect is None:
        return {"ok": False, "error": "Whole-program Ghidra export is unavailable."}
    target = {"locator": context.get("locator", ""), "programPath": context.get("program", "")}
    def payload(log: str) -> dict[str, Any]:
        try:
            data, _ = json.JSONDecoder().raw_decode(log[log.index("{"):])
            if isinstance(data, dict) and isinstance(data.get("result"), str):
                data = json.loads(data["result"])
            return data if isinstance(data, dict) else {}
        except (ValueError, TypeError):
            return {}
    # Inspection and export must retain one project/session ownership interval.
    with CONTEXT_LOCK:
        code, log = _mcp_executor_in_context(inspect, {**target, "_preparationProbe": True, "code":
            "import json\nfrom agentdecompile_cli.mcp_utils.program_analysis import program_needs_analysis\n"
            "__result__ = json.dumps({'md5': str(currentProgram.getExecutableMD5()), 'needsAnalysis': program_needs_analysis(currentProgram), "
            "'functionCount': int(currentProgram.getFunctionManager().getFunctionCount()), 'project': str(currentProgram.getDomainFile().getProjectLocator()), 'program': str(currentProgram.getDomainFile().getPathname())})",
            "timeout": 30}, cancel, trusted_preparation_probe=True)
        observed = payload(log)
        if code or not observed.get("md5") or str(observed["md5"]).lower() != str(context.get("programFingerprint", "")).lower():
            return {"ok": False, "error": "The selected Ghidra program's fingerprint could not be matched to this binary.", "observation": observed}
        if observed.get("needsAnalysis") is not False:
            return {"ok": False, "error": "Analysis is pending. Whole-program source export will be available after analysis completes.", "observation": observed}
        export_format = _ghidra_export_format_for(default_source_language())
        code, log = _mcp_executor_in_context(
            export,
            {**target, "outputPath": str(output_path), "format": export_format, "createHeader": True},
            cancel,
        )
        data = payload(log)
    accepted = code == 0 and data.get("success") is True and output_path.is_file()
    return {"ok": accepted, "tool": "export", "data": data, "observation": observed,
            "error": "" if accepted else data.get("error") or log[-4000:]}


def _bounded_archive_export(
    output_path: Path,
    context: dict[str, Any],
    cancel: threading.Event,
    deadline: float,
) -> dict[str, Any]:
    """Bound an uninterruptible live MCP call without publishing uncertain output."""
    result: queue.SimpleQueue[dict[str, Any]] = queue.SimpleQueue()
    def run() -> None:
        try:
            result.put(_export_archive_program(output_path, context, cancel))
        except BaseException as exc:
            result.put({'ok': False, 'error': str(exc)})
    worker = threading.Thread(target=run, name='source-archive-live-export', daemon=True)
    worker.start()
    while worker.is_alive():
        if cancel.is_set() or time.monotonic() >= deadline:
            return {
                'ok': False,
                'quarantined': True,
                'ownershipResolved': False,
                'error': ('Source archive cancelled while the live MCP export remained in flight; '
                          if cancel.is_set() else 'Source archive deadline expired while the live MCP export remained in flight; ')
                         + 'staging is quarantined and no archive was published.',
            }
        worker.join(min(.1, max(0.0, deadline - time.monotonic())))
    value = result.get()
    value['ownershipResolved'] = True
    return value


def _mcp_executor(
    action: ActionSpec,
    params: dict[str, Any],
    cancel: threading.Event,
    *,
    trusted_preparation_facts_inventory: bool = False,
    trusted_preparation_probe: bool = False,
) -> tuple[int, str]:
    # Do not hold CONTEXT_LOCK across the loopback MCP HTTP request.  The MCP
    # handler uses the same lock while serving that request; holding it here
    # makes a dashboard job wait forever for its own request to acquire the
    # lock.  Each bridge operation serializes its own session-critical call.
    with MCP_EXECUTOR_LOCK:
        return _mcp_executor_in_context(
            action,
            params,
            cancel,
            trusted_preparation_facts_inventory=trusted_preparation_facts_inventory,
            trusted_preparation_probe=trusted_preparation_probe,
        )


def _mcp_executor_in_context(
    action: ActionSpec,
    params: dict[str, Any],
    cancel: threading.Event,
    *,
    trusted_preparation_facts_inventory: bool = False,
    trusted_preparation_probe: bool = False,
) -> tuple[int, str]:
    from agentdecompile_recovery.corpus.dashboard.mcp_bridge import call_tool, ensure_program, ensure_project, reset_session

    if cancel.is_set():
        return 1, "[cancelled]\n"
    arguments = {
        key: value
        for key, value in params.items()
        if (value not in (None, "") or (value == "" and action.command == "manage-function" and str(params.get("mode", "")).replace("_", "").replace("-", "").lower() == "setproperties" and key.replace("_", "").lower() in {"namespace", "callfixup", "thunktarget"})) and key in {field.name for field in action.fields}
    }
    locator = str(params.get("locator") or "")
    if locator and action.command not in {"open", "connect-shared-project"}:
        opened = ensure_project(locator)
        if not opened.get("ok"):
            return 1, "Could not open the selected project without analysis.\n" + str(opened.get("error") or opened.get("text"))
        if cancel.is_set():
            return 1, "[cancelled before action]\n"
    # Opening a project does not make a nested program current in the MCP
    # session.  Script and analysis tools operate on ``currentProgram``; if
    # we skip this step they can either use a stale selection or reject a
    # folder-qualified program path as though the program did not exist.
    # ``ensure_program`` uses the project's canonical path, checks it out,
    # and keeps the session target aligned with this job.
    program = str(params.get("programPath") or params.get("program") or "").strip()
    needs_program = action.command in {
        "analyze-program", "execute-script", "get-function", "decompile-function",
        "list-functions", "list-symbols", "list-types", "export",
    }
    if locator and program and needs_program:
        # Only the in-process preparation facts inventory receives this
        # privilege. Request parameters are untrusted, including private-
        # looking names such as _readOnlyGhidra.
        exclusive = action.command == "analyze-program" or (
            action.mutating and not bool(
                trusted_preparation_probe or trusted_preparation_facts_inventory
            )
        )
        ensured = ensure_program(
            locator,
            program,
            require_live=True,
            exclusive=exclusive,
            include_inventory=False,
        )
        if not ensured.get("ok"):
            detail = ensured.get("error") or ensured.get("steps") or "program could not be opened"
            return 1, f"Could not make {program} current in the selected project.\n{detail}\n"
        program = str(ensured.get("program_path") or program)
        if "programPath" in arguments:
            arguments["programPath"] = program
        elif "program" in arguments:
            arguments["program"] = program
        if cancel.is_set():
            return 1, "[cancelled before program action]\n"
    if trusted_preparation_probe and action.command == "execute-script":
        arguments["autoPrereqInvocation"] = True
    if params.get('_functionEvidence') and action.command == 'get-function':
        arguments['autoPrereqInvocation'] = True
    arguments["responseFormat"] = "json"
    timeout = 600.0 if action.long_running else 120.0
    if action.command in {"analyze-program", "import-binary", "export"}:
        timeout = 1800.0
    if action.command == "execute-script":
        timeout = min(1800.0, max(timeout, float(arguments.get("timeout", 30)) + 30.0))
    # Preparation probes are read-only health checks.  Keep their network
    # wait bounded independently of the workflow's 900-second drain budget;
    # a wedged Ghidra request must not leave a probe job looking active for
    # the lifetime of the coordinator.  The MCP server may finish its own
    # request later, but this job records the timeout and the workflow can
    # route the named failure without replaying a mutation.
    if trusted_preparation_probe:
        try:
            probe_timeout = float(os.environ.get("AGENT_DECOMPILE_PROBE_TIMEOUT_SECONDS", "90"))
        except ValueError:
            probe_timeout = 90.0
        timeout = min(timeout, max(15.0, probe_timeout))
    hit = call_tool(action.command, arguments, timeout=timeout)
    # A Ghidra MCP restart invalidates the HTTP session but does not mean the
    # requested script ran.  Re-open the project and selected program once,
    # then replay that unaccepted request.  Without this recovery a long
    # automatic preparation wave quietly accumulates transient failures until
    # an operator manually restarts it.
    missing_session = "missing session id" in str(hit.get("error") or "").casefold()
    if missing_session and not cancel.is_set():
        reset_session()
        reopened = ensure_project(locator) if locator else {"ok": True}
        if reopened.get("ok") and locator and program and needs_program:
            reopened = ensure_program(
                locator,
                program,
                require_live=True,
                exclusive=exclusive,
                include_inventory=False,
            )
        if reopened.get("ok"):
            hit = call_tool(action.command, arguments, timeout=timeout)
        else:
            hit = {
                "ok": False,
                "error": "Ghidra MCP session reset, but the selected project/program could not be restored: "
                + str(reopened.get("error") or reopened.get("steps") or "unknown restore failure"),
                "text": "",
                "parsed": None,
            }
    text = hit.get("text") or ""
    parsed = hit.get("parsed")
    if (
        action.command == "analyze-program"
        and isinstance(parsed, dict)
        and parsed.get("alreadyAnalyzed") is True
    ):
        # Ghidra rejects redundant analysis, but that is the successful reuse
        # path for an existing analyzed project, not a failed dashboard job.
        parsed = {**parsed, "success": True, "reusedExistingAnalysis": True}
        hit = {**hit, "ok": True, "isError": False, "error": "", "parsed": parsed}
        text = json.dumps(parsed, default=str)
    if hit.get("ok") and isinstance(parsed, dict) and action.command in {"get-function", "decompile-function"}:
        from agentdecompile_recovery.corpus.dashboard.function_evidence import record
        record({**params, "programPath": program}, action.command, parsed)
    log_parts = [f"mcp {action.command}\n"]
    if parsed is not None:
        log_parts.append(json.dumps(parsed, indent=2, default=str)[: MAX_LOG_BYTES - 200])
        log_parts.append("\n")
    elif text:
        log_parts.append(text[: MAX_LOG_BYTES - 200])
        log_parts.append("\n")
    if hit.get("error"):
        log_parts.append(f"error: {hit['error']}\n")
    if hit.get('ok') and action.mutating and params.get('programPath') and not params.get('_preparationProbe') and not action.command.startswith(('get-', 'list-', 'search-', 'decompile-')) and action.command != 'export':
        from agentdecompile_recovery.corpus.dashboard.function_evidence import invalidate
        try:
            invalidate(params)
        except OSError as exc:
            log_parts.append(f'Function evidence refresh could not be recorded: {exc}\n')
    if (hit.get('ok') and action.mutating and _auto_checkin_enabled()
            and not params.get('_preparationProbe')
            and _tool_key(action.command) in _DASHBOARD_AUTO_CHECKIN_TOOLS
            and action.command not in {'checkin-program', 'checkout-program', 'open', 'connect-shared-project', 'close'}):
        program = str(params.get('programPath') or params.get('program') or '')
        if not program:
            log_parts.append('checkin-program skipped: no programPath in job params\n')
        else:
            checkin = call_tool('checkin-program', {'programPath': program}, timeout=120.0)
            if checkin.get('ok'):
                log_parts.append('checkin-program: project changes saved\n')
            else:
                error = checkin.get('error') or 'checkin-program failed'
                log_parts.append(f'checkin-program warning: {error}\n')
    if cancel.is_set():
        return 1, "".join(log_parts) + "[cancelled]\n"
    return (0 if hit.get("ok") else 1), "".join(log_parts)


def isolated_job_env(argv: list[str], base: dict[str, str] | None = None) -> dict[str, str]:
    """Objdiff uses the recovery-toolchains dir and drops Wine from ghidra-bulk."""
    env = dict(base if base is not None else os.environ)
    if not any("objdiff-check" in str(part) for part in argv):
        return env
    env["AGENT_DECOMPILE_OBJDIFF_ISOLATED"] = "1"
    env.pop("WINEPREFIX", None)
    env.pop("WINE", None)
    repo = Path(__file__).resolve().parents[5]
    tool = repo / "scripts" / "recovery-toolchains"
    if tool.is_dir():
        env["PATH"] = str(tool) + os.pathsep + env.get("PATH", "")
    return env


def _default_executor(
    argv: list[str],
    cwd: Path,
    cancel: threading.Event,
    *,
    on_output: Callable[[str], None] | None = None,
    timeout_seconds: float | None = None,
    unlimited: bool = False,
) -> tuple[int, str]:
    """Drain output without blocking cancellation when a child is silent."""
    if not argv:
        return 2, "empty command"
    proc = subprocess.Popen(argv, cwd=str(cwd), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1, env=isolated_job_env(argv),
        start_new_session=os.name != "nt")
    lines: queue.Queue[str | None] = queue.Queue(maxsize=1000)
    def read() -> None:
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                lines.put(line)
        finally:
            lines.put(None)
    threading.Thread(target=read, daemon=True).start()
    log = ""
    configured_timeout = timeout_seconds
    if not unlimited and configured_timeout is None:
        try:
            configured_timeout = float(os.environ.get("AGENT_DECOMPILE_JOB_TIMEOUT_SECONDS", "1800"))
        except ValueError:
            configured_timeout = 1800.0
    deadline = None if unlimited else time.monotonic() + max(1.0, float(configured_timeout))
    cancellation_at = None
    cancellation_forced = False
    exited_at = None
    timed_out = False
    while True:
        now = time.monotonic()
        if deadline is not None and now >= deadline and cancellation_at is None:
            timed_out = True
            cancellation_at = now
            log += f"\n[timed out after {configured_timeout:g} seconds]\n"
        if cancel.is_set() and cancellation_at is None:
            cancellation_at = now
            log += "\n[cancelled]\n"
        if cancellation_at is not None and not cancellation_forced:
            try:
                if os.name != "nt":
                    os.killpg(proc.pid, signal.SIGTERM)
                elif proc.poll() is None:
                    proc.terminate()
            except ProcessLookupError:
                pass
        if cancellation_at is not None and not cancellation_forced and now - cancellation_at >= 5:
            cancellation_forced = True
            try:
                if os.name != "nt":
                    os.killpg(proc.pid, signal.SIGKILL)
                elif proc.poll() is None:
                    proc.kill()
            except ProcessLookupError:
                pass
        returncode = proc.poll()
        if returncode is not None:
            exited_at = exited_at or now
        if (cancellation_forced and now - (cancellation_at or now) >= 7) or (
            exited_at is not None and now - exited_at >= 2
        ):
            # A descendant can retain stdout after the leader exits, and a
            # D-state child cannot be killed until kernel I/O returns. Never
            # hold the job worker forever waiting for a pipe EOF in either case.
            if proc.stdout is not None:
                proc.stdout.close()
            break
        try:
            line = lines.get(timeout=.1)
        except queue.Empty:
            # Process exit can precede the reader thread delivering its final
            # buffered output. Only the pipe EOF sentinel proves it is drained.
            continue
        if line is None:
            break
        log = (log + line)[-MAX_LOG_BYTES:]
        if on_output: on_output(log)
    returncode = proc.poll()
    if returncode is None:
        try:
            returncode = proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            returncode = None
    if returncode is None:
        return 124, log + "\n[process did not reach a terminal state; ownership remains unresolved]\n"
    return (124 if timed_out else int(returncode)), log


STORE = JobStore()


def identity_lock_key(params: dict[str, Any] | None) -> str | None:
    raw = (params or {}).get("db") or live_db()
    if not raw:
        return None
    try:
        return str(Path(raw).expanduser().resolve())
    except (OSError, RuntimeError, TypeError, ValueError):
        return None


def match_pair_lock_key(params: dict[str, Any] | None) -> str | None:
    """Serialize only duplicate directed comparisons against one corpus DB."""
    row = params or {}
    db = identity_lock_key(row)
    if not db:
        return None
    return json.dumps([db, str(row.get("run") or ""), str(row.get("src") or ""), str(row.get("dst") or "")])


def ghidra_lock_key(params: dict[str, Any] | None) -> str:
    row = params or {}
    return str(row.get("locator") or row.get("programPath") or row.get("program") or "")


def _active_duplicate(action_id: str, params: dict[str, Any]) -> JobRecord | None:
    """Return an existing active job targeting the same work directory.

    Recovery outputs are append-only ledgers; admitting two writers corrupts
    reuse accounting and doubles compiler work.
    """
    target = str(params.get("workDir") or params.get("work_dir") or "").strip()
    if not target:
        return None
    try:
        target_key = str(Path(target).expanduser().resolve())
    except (OSError, RuntimeError, ValueError):
        target_key = target
    for existing in STORE.list(compact=True):
        if existing.action_id != action_id or existing.status not in {"queued", "running", "cancelling"}:
            continue
        other = str(existing.params.get("workDir") or existing.params.get("work_dir") or "").strip()
        try:
            other = str(Path(other).expanduser().resolve())
        except (OSError, RuntimeError, ValueError):
            pass
        if other and other == target_key:
            return existing
    return None


def _external_pipeline_owner(action_id: str, params: dict[str, Any]) -> dict[str, str] | None:
    """Find a non-dashboard recovery owner for the same db/workspace.

    Dashboard receipts are not process handles, but the recovery services are.
    Refuse a second writer rather than treating their state as resumable.
    """
    if not any(token in action_id for token in (
        "verify", "recovery-orchestrator", "cross-place", "consolidate",
    )):
        return None
    db = str(params.get("db") or "").strip()
    work_dir = str(params.get("workDir") or params.get("work_dir") or params.get("out-dir") or "").strip()
    if not db or not work_dir:
        return None
    try:
        db = str(Path(db).expanduser().resolve())
        work_dir = str(Path(work_dir).expanduser().resolve())
    except (OSError, RuntimeError, ValueError):
        return None
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or proc.name == str(os.getpid()):
            continue
        try:
            argv = proc.joinpath("cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if "agentdecompile_recovery.corpus.cli" not in argv:
            continue
        if db in argv and work_dir in argv:
            return {"pid": proc.name, "argv": argv[:1024]}
    return None


def start_job(
    action_id: str,
    params: dict[str, Any] | None = None,
    *,
    context: dict[str, Any] | None = None,
    confirm: bool = False,
    dry_run: bool = False,
    _trusted_context: object | None = None,
) -> tuple[dict[str, Any], int]:
    action = action_by_id(action_id)
    if action is None:
        return {"error": f"unknown action {action_id}"}, 404
    filled = apply_defaults(action, dict(params or {}), context)
    duplicate = _active_duplicate(action.id, filled)
    if duplicate is not None and not dry_run:
        return {"ok": True, "deduplicated": True, "job": duplicate.to_dict()}, 202
    errors = validate_params(action, filled, confirm=confirm)
    if errors:
        return {"error": "; ".join(errors), "actionId": action.id}, 400
    owner = _external_pipeline_owner(action.id, filled)
    if owner is not None and not dry_run:
        return {
            "ok": False,
            "actionId": action.id,
            "error": "External pipeline already owns this database and workspace; inspect or adopt it before starting another writer.",
            "externalOwner": owner,
        }, 409
    if action.id in IDENTITY_WRITERS or action.id == "corpus.match-pair":
        key = identity_lock_key(filled)
        if not key:
            return {"error": "identity writer needs --db", "actionId": action.id}, 400
        filled["db"] = key
    if action.backend == "preparation" and not dry_run:
        from agentdecompile_recovery.corpus.dashboard.preparation import submit
        try:
            run = submit(filled, resume=bool(filled.get("resume", False)))
        except (ValueError, OSError) as exc:
            return {"error": str(exc)}, 400
        job = get_job(run.get("jobId", ""))
        return {"ok": run["status"] != "blocked", "run": run, "job": job.to_dict() if job else {"id": run.get("jobId", ""), "status": run["status"]}}, 202
    argv = build_command(action, filled)
    if dry_run:
        return {"ok": True, "dryRun": True, "action": action.to_dict(), "argv": argv, "params": filled}, 200
    job = STORE.start(
        action,
        filled,
        argv,
        trusted_preparation_facts_inventory=(
            _trusted_context is _PREPARATION_FACTS_INVENTORY
            and action.id == "mcp.execute-script"
        ),
        trusted_preparation_probe=(
            _trusted_context is _PREPARATION_PROBE
            and action.id == "mcp.execute-script"
        ),
    )
    return {"ok": True, "job": job.to_dict()}, 202


def _start_preparation_facts_inventory(
    params: dict[str, Any], context: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    """Submit the preparation-owned, read-only inventory script."""
    return start_job(
        "mcp.execute-script",
        params,
        context=context,
        confirm=True,
        _trusted_context=_PREPARATION_FACTS_INVENTORY,
    )


def _start_preparation_probe(
    params: dict[str, Any], context: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    """Submit a preparation-owned, bounded read-only probe."""
    return start_job(
        "mcp.execute-script",
        params,
        context=context,
        confirm=True,
        _trusted_context=_PREPARATION_PROBE,
    )


def list_jobs(*, compact: bool = False) -> list[JobRecord]:
    return STORE.list(compact=compact)


def get_job(job_id: str, *, compact: bool = False) -> JobRecord | None:
    return STORE.get(job_id, compact=compact)


def cancel_job(job_id: str) -> JobRecord | None:
    return STORE.cancel(job_id)
