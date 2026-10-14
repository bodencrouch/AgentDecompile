"""In-process job runner for cataloged dashboard actions."""

from __future__ import annotations

import json
import hashlib
import math
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

from agentdecompile_recovery.corpus.dashboard.mcp_bridge import CONTEXT_LOCK, ownership_metadata

# Audited local SQLite-only action; other providers need their own complete
# lifecycle proof (a clear Python session cannot prove remote/Wine clearance).
LOCAL_RECONCILIATION_ACTIONS = frozenset({'corpus.logical-build'})

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
    admission_wait: str = ''
    log_truncated: bool = False
    work_progress: dict[str, Any] | None = None
    trusted_preparation_facts_inventory: bool = False
    trusted_preparation_probe: bool = False
    mcp_reserve: Callable[[str], Any] | None = field(default=None, repr=False, compare=False)
    preparation_authority: Any = field(default=None, repr=False, compare=False)
    resource_disposition: str = "unreserved"
    resource_keys: dict[str, Any] = field(default_factory=dict)
    execution_attempt: str = field(default_factory=lambda: uuid.uuid4().hex)
    execution_root: str = ""
    execution_owner: dict[str, Any] = field(default_factory=dict)
    clearance_observation: dict[str, Any] = field(default_factory=dict)
    no_dispatch_observation: dict[str, Any] = field(default_factory=dict)
    cross_place_generation: dict[str, Any] = field(default_factory=dict)

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
            "resourceDisposition": self.resource_disposition,
            "admissionWait": self.admission_wait,
            "resourceKeys": _json_safe(self.resource_keys),
            "executionAttempt": self.execution_attempt,
            "executionRoot": self.execution_root,
            "executionOwner": _json_safe(self.execution_owner),
            "clearanceObservation": _json_safe(self.clearance_observation),
            "noDispatchObservation": _json_safe(self.no_dispatch_observation),
            "crossPlaceGeneration": _json_safe(self.cross_place_generation),
            "ownershipUnresolved": self.resource_disposition == "quarantined",
            "historyOnly": self.history_only,
            "ownerUnavailable": self.owner_unavailable,
            "workerPid": self.execution_owner.get("pid"),
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


def _read_only_supervisor_status(action_id: str, params: dict) -> bool:
    return action_id == "corpus.recovery-orchestrator" and type(params.get("status")) is bool and params["status"]


# Only audited local, synchronous action implementations belong here. The
# snapshot CLI's --destination maps to exporter output_dir; it reads SQLite
# and writes this tree in its own process, without launching provider children.
_EXTERNAL_ACTION_CONTRACTS = {
    "corpus.export-reagent-snapshot": (("output", "destination"),),
    "recover.verify-package": (("output", "out-dir"),),
    "corpus.cross-place": (("output", "out-dir"),),
}
_EXTERNAL_RESOURCE_KINDS = frozenset({"compiler", "wineprefix", "project", "output", "store"})


def _paths_overlap(left: str, right: str) -> bool:
    a, b = Path(left), Path(right)
    return a == b or a in b.parents or b in a.parents


def _external_contract_matches(action_id: str, params: dict, keys: dict, root: Path) -> bool:
    contract = _EXTERNAL_ACTION_CONTRACTS.get(action_id)
    if not contract:
        return False
    expected = [[kind, _canonical_resource_path(params.get(name), base=root)] for kind, name in contract]
    if action_id == 'corpus.cross-place':
        # Shared SQLite reader and refreshable versioned inputs; only the
        # derived candidate tree is exclusively owned for the watch lifetime.
        expected = [['output', str(Path(expected[0][1]) / '.cross-place')]] if expected[0][1] else []
    return all(value for _, value in expected) and keys.get("external") == sorted(expected)


def _bound_clearance(row: dict) -> bool:
    if row.get("actionId") == "recover.verify-package":
        from agentdecompile_recovery.native_verify_contract import command_matches
        if not command_matches(row.get("argv"), row.get("params") or {}):
            return False
    if row.get("actionId") == "corpus.cross-place":
        from agentdecompile_recovery.corpus.cross_place import command_matches
        if not command_matches(row.get("argv"), row.get("params") or {}):
            return False
    proof, owner = row.get("clearanceObservation"), row.get("executionOwner")
    if not isinstance(proof, dict) or not isinstance(owner, dict) or not owner:
        return False
    expected = {"jobId": row.get("id"), "attempt": row.get("executionAttempt"),
                "resourceKeys": row.get("resourceKeys"), "process": owner,
                "argvDigest": hashlib.sha256(json.dumps(row.get("argv"), separators=(",", ":")).encode()).hexdigest()}
    return (bool(row.get("executionAttempt")) and all(proof.get(k) == v for k, v in expected.items())
            and proof.get("source") == "local-executor-session-observer-v1"
            and proof.get("sessionClearance") == "clear"
            and type(owner.get("pid")) is int and bool(owner.get("start_ticks")) and bool(owner.get("boot_id")))


def _cross_place_preparation_binding(row: dict) -> dict:
    return {'jobId': row.get('id'), 'attempt': row.get('executionAttempt'),
            'executionRoot': row.get('executionRoot'), 'resourceKeys': row.get('resourceKeys'),
            'argvDigest': hashlib.sha256(json.dumps(row.get('argv'), separators=(',', ':')).encode()).hexdigest(),
            'paramsDigest': hashlib.sha256(json.dumps(row.get('params'), sort_keys=True, separators=(',', ':')).encode()).hexdigest()}


def _cross_place_preparing(row: dict) -> bool:
    from agentdecompile_recovery.corpus.cross_place import command_matches
    generation = row.get('crossPlaceGeneration') or {}
    return (row.get('actionId') == 'corpus.cross-place' and generation.get('version') == 1
            and generation.get('phase') == 'preparing'
            and generation.get('binding') == _cross_place_preparation_binding(row)
            and not row.get('executionOwner') and not row.get('clearanceObservation')
            and command_matches(row.get('argv'), row.get('params') or {}))


def _cross_place_reconciliation_scope(row: dict) -> str | None:
    """Validate retained launch/scope without opening a DB or minting clearance."""
    from agentdecompile_recovery.corpus import cross_place, cross_place_checkpoint as checkpoint
    from agentdecompile_recovery.corpus.cross_place_admission import regular
    try:
        if row.get('actionId') != 'corpus.cross-place': return 'not_cross_place'
        params, generation, keys = row['params'], row['crossPlaceGeneration'], row['resourceKeys']
        if not _external_contract_matches('corpus.cross-place', params, keys, Path(row['executionRoot'])):
            return 'qualified_external_resource_contract'
        if not cross_place.command_matches(row['argv'], params): return 'qualified_guarded_generation'
        if _cross_place_preparing(row): return None
        envelope = json.loads(row['argv'][-1])['generation']
        if (generation.get('version') != 1 or generation.get('envelope') != envelope
                or envelope.get('version') != 1
                or generation.get('generation') != row['executionAttempt']
                or envelope.get('generation') != row['executionAttempt']
                or generation.get('phase') not in {'intent', 'undispatched', 'dispatch-possible', 'cleared'}):
            return 'exact_generation_binding'
        area = Path(params['out-dir']) / '.cross-place'
        lease = envelope['lease']
        if lease.get('root') != str(area) or type(lease.get('fd')) is not int or lease['fd'] < 3:
            return 'exact_output_lease_scope'
        info = regular(area / '.owner.lock').stat()
        if (lease.get('device'), lease.get('inode')) != (info.st_dev, info.st_ino):
            return 'unchanged_output_lease_identity'
        area_info = area.stat()
        scope = checkpoint.read(area / 'checkpoint/scope.json')
        if scope != {'schema': checkpoint.SCHEMA, 'area': str(area),
                     'device': area_info.st_dev, 'inode': area_info.st_ino}:
            return 'unchanged_checkpoint_scope'
        scan_path = area / 'checkpoint/scan.json'
        scan = checkpoint.read(scan_path)
        expected = {'repo': params['repo'], 'db': params['db'], 'raw': params['raw-dir'],
                    'receipt': params['byteexact-receipt'],
                    'exploration': bool(params.get('no-compile-gate'))}
        if scan.get('schema') != checkpoint.SCHEMA or scan.get('scope', {}).get('parameters') != expected:
            return 'exact_checkpoint_parameters'
        scan_scope = scan['scope']
        source_value = scan_scope.get('source')
        if not isinstance(source_value, str): return 'exact_checkpoint_source_path'
        source = Path(source_value)
        if (not source.is_absolute() or any(part.is_symlink() for part in [source, *source.parents])
                or source_value != str(source.resolve(strict=True))):
            return 'exact_checkpoint_source_path'
        actual_source = cross_place.selected_source(params)
        if actual_source is None or source != actual_source.resolve(strict=True):
            return 'exact_checkpoint_source_path'
        source_info = source.stat()
        if (not source.is_dir() or type(scan_scope.get('device')) is not int
                or type(scan_scope.get('inode')) is not int
                or (scan_scope['device'], scan_scope['inode']) != (source_info.st_dev, source_info.st_ino)):
            return 'exact_checkpoint_source_identity'
        if not re.fullmatch(r'[0-9a-f]{64}', envelope.get('scanDigest', '')):
            return 'valid_scan_intent'
        if _cross_place_not_dispatched(row) and hashlib.sha256(scan_path.read_bytes()).hexdigest() != envelope['scanDigest']:
            return 'unchanged_undispatched_scan_intent'
        return None
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return 'readable_bound_generation_scope'


def _cross_place_not_dispatched(row: dict) -> bool:
    """A committed generation intent cannot be reused as child clearance."""
    from agentdecompile_recovery.corpus.cross_place import command_matches
    generation = row.get('crossPlaceGeneration') or {}
    if _cross_place_preparing(row): return True
    if (row.get('actionId') != 'corpus.cross-place' or generation.get('version') != 1
            or generation.get('phase') not in ('intent', 'undispatched')
            or generation.get('generation') != row.get('executionAttempt')
            or row.get('executionOwner') or row.get('clearanceObservation')
            or not command_matches(row.get('argv'), row.get('params') or {})):
        return False
    try:
        envelope = json.loads(row['argv'][-1])['generation']
        if envelope != generation['envelope']: return False
    except (ValueError, TypeError, KeyError): return False
    prior = generation.get('priorClearance')
    return prior is None or (prior.get('id') == row.get('id')
        and prior.get('params') == row.get('params')
        and prior.get('resourceKeys') == row.get('resourceKeys') and _bound_clearance(prior))


def _native_no_dispatch_binding(row: dict) -> dict:
    return {"source": "catalog-native-before-dispatch-v1", "jobId": row.get("id"),
            "actionId": row.get("actionId"), "attempt": row.get("executionAttempt"),
            "executionRoot": row.get("executionRoot"), "status": row.get("status"),
            "argvDigest": hashlib.sha256(json.dumps(row.get("argv"), separators=(",", ":")).encode()).hexdigest(),
            "paramsDigest": hashlib.sha256(json.dumps(row.get("params"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


def _native_not_dispatched(row: dict) -> bool:
    """A durable predispatch phase is distinct from compiler-session clearance."""
    return (row.get("actionId") in {"recover.verify-package", "corpus.cross-place"}
            and row.get("status") in {"queued", "cancelling", "failed", "cancelled"}
            and row.get("resourceDisposition") == "unreserved" and not row.get("resourceKeys")
            and not row.get("executionOwner") and not row.get("clearanceObservation")
            and not row.get("startedAt")
            and bool(row.get("executionAttempt")) and bool(row.get("executionRoot"))
            and row.get("noDispatchObservation") == _native_no_dispatch_binding(row))


def _observe_native_no_dispatch(job: JobRecord) -> None:
    if job.action_id in {"recover.verify-package", "corpus.cross-place"}:
        job.no_dispatch_observation = _native_no_dispatch_binding(job.to_dict())


def _canonical_resource_path(value: Any, *, base: Path) -> str | None:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        return None
    try:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = base / path
        return str(path.resolve(strict=False))
    except (OSError, RuntimeError, TypeError, ValueError):
        return None


def _external_resource_entries(action: ActionSpec | None, params: dict, *, base: Path | None = None) -> tuple[tuple[str, str], ...]:
    if action is None:
        return ()
    if action.id == 'review.decide':
        from .match_review import resource_paths
        return tuple(('store', str(path)) for path in sorted(resource_paths(params['db'])))
    contract = _EXTERNAL_ACTION_CONTRACTS.get(action.id, ())
    base = base or (live_root() or Path.cwd()).resolve()
    claims = []
    for kind, name in contract:
        value = _canonical_resource_path(params.get(name), base=base)
        if value is None:
            raise ValueError(f"{action.id} requires resource parameter {name}")
        claims.append((kind, value))
    if action.id == 'corpus.cross-place':
        claims = [('output', str(Path(claims[0][1]) / '.cross-place'))]
    return tuple(sorted(claims))


def _resource_keys(action: ActionSpec | None, params: dict, *, base: Path | None = None) -> dict:
    if action is None or _read_only_supervisor_status(action.id, params):
        return {}
    keys = {}
    identity = identity_lock_key(params) or ""
    if action.identity_scope == "database" and identity:
        keys["identity"] = identity
    elif action.identity_scope == "pair" and identity:
        pair = match_pair_lock_key(params)
        if pair:
            keys["pair"] = [identity, pair]
    if action.ghidra_exclusive or (action.backend == "mcp-cli" and action.mutating):
        keys["ghidra"] = ghidra_lock_key(params)
    external = _external_resource_entries(action, params, base=base)
    if external:
        keys["external"] = [[kind, value] for kind, value in external]
    return keys


def _ownership_unresolved(log: str) -> bool:
    if "ownership remains unresolved" in log:
        return True
    def unresolved(value: Any, depth: int = 0) -> bool:
        if depth > 8:
            return True  # unknown deeply nested adapter envelope cannot clear access
        if isinstance(value, dict):
            return (value.get('ownershipResolved') is False or bool(value.get('ownershipUnresolved'))
                    or any(unresolved(item, depth + 1) for item in value.values()))
        if isinstance(value, list):
            return any(unresolved(item, depth + 1) for item in value)
        if isinstance(value, str) and value.lstrip().startswith(('{', '[')):
            try:
                return unresolved(json.loads(value), depth + 1)
            except ValueError:
                return False
        return False
    # Progress JSON may precede a terminal envelope; inspect every JSON object
    # rather than letting the first unrelated observation conceal quarantine.
    decoder = json.JSONDecoder()
    for match in re.finditer(r'\{', log):
        try:
            payload, _ = decoder.raw_decode(log, match.start())
            if unresolved(payload):
                return True
        except ValueError:
            continue
    return False


def _ownership_note(value: Any) -> str:
    # Bridge responses repeat the payload under raw.content/text/parsed. Use
    # provider-depth accounting here; the final log scanner sees the emitted
    # provider body without those duplicated transport wrappers.
    serialized = json.dumps(value, default=str)
    unresolved = ('ownership remains unresolved' in serialized
                  or (bool(ownership_metadata(value)) if isinstance(value, dict)
                      else _ownership_unresolved(serialized)))
    return ('\n{"ownershipResolved":false,"ownershipUnresolved":true}\n' if unresolved else '')


class JobStore:
    """One serving workbench owner; resource maps are not a multi-server lease.

    Durable receipts preserve reservations across sequential owner restart.
    A receipt-root flock excludes another scoped JobStore on that same root.
    Different receipt roots sharing an external corpus still need external
    ownership corroboration; this is not distributed provider fencing.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}
        self._order: list[str] = []
        self._cancels: dict[str, threading.Event] = {}
        self._running = 0
        self._identity_held: dict[str, str] = {}
        self._pair_held: dict[tuple[str, str], str] = {}
        self._ghidra_held: dict[str, str] = {}
        self._external_held: dict[tuple[str, str], str] = {}
        self.executor: Executor | None = None
        self._resource_owner_handle = None
        self._cross_leases = {}
        self._cross_active: set[str] = set()
        self._resource_root_key: str | None = None
        self._restored_root: str | None = None
        self._receipt_versions: dict[str, int] = {}
        self._persisted_at: dict[str, float] = {}
        self._persist_pending: dict[str, dict[str, Any]] = {}
        self._persist_lock = threading.Lock()
        self._persist_wake = threading.Event()
        threading.Thread(target=self._persist_loop, name="dashboard-job-receipts", daemon=True).start()

    def _persist_locked(self, job: JobRecord, *, force: bool = False) -> None:
        """Resource intents commit synchronously in the existing receipt store."""
        from . import job_history
        from agentdecompile_recovery.corpus.supervision import save_state
        now = time.monotonic()
        if not force and now - self._persisted_at.get(job.id, 0) < .1:
            return
        payload = job.to_dict()
        payload.update(updatedAt=time.time(), **job_history.owner())
        self._persisted_at[job.id] = now
        with self._persist_lock:
            version = self._receipt_versions.get(job.id, 0) + 1
            self._receipt_versions[job.id] = version
            payload['receiptVersion'] = version
            if job.resource_keys or job.no_dispatch_observation:
                root = job_history.directory()
                if root is None:
                    raise OSError('Durable resource admission requires a workbench receipt directory')
                root.mkdir(parents=True, exist_ok=True, mode=0o700)
                self._persist_pending.pop(job.id, None)
                save_state(root / (job.id + '.json'), payload)
            else:
                self._persist_pending[job.id] = payload
                self._persist_wake.set()

    def _persist_loop(self) -> None:
        from . import job_history
        while True:
            # A failed flush retries on a timer; the receipt is never dropped.
            self._persist_wake.wait(timeout=2.0 if getattr(self, '_store_failure', None) else None)
            self._persist_wake.clear()
            with self._persist_lock:
                pending, self._persist_pending = self._persist_pending, {}
            failure = None
            for job_id, payload in pending.items():
                try:
                    with self._persist_lock:
                        if payload.get('receiptVersion') != self._receipt_versions.get(job_id):
                            continue
                        job_history.write(payload)
                except OSError as exc:
                    failure = f'{type(exc).__name__}: {exc}'
                    with self._persist_lock:
                        # Keep the newest version queued for the next attempt.
                        self._persist_pending.setdefault(job_id, payload)
                    with self._lock:
                        job = self._jobs.get(job_id)
                        if job is not None:
                            job.log_reason = f'Durable job output could not be saved yet (retrying): {exc}'
            with self._persist_lock:
                backlog = bool(self._persist_pending)
            self._store_failure = (time.time(), failure) if failure else (
                getattr(self, '_store_failure', None) if backlog else None)

    def event_store_health(self) -> dict[str, Any]:
        """Whether the sole durable job-event store can accept new unsafe work (FP-18).

        Healthy means the receipt directory is writable now and no earlier receipt is still
        waiting on a failed flush, so acceptance resumes only after continuity is restored.
        """
        from . import job_history
        root = job_history.directory()
        if root is None:
            return {'ok': False, 'reason': 'no workbench receipt directory is configured'}
        failure = getattr(self, '_store_failure', None)
        if failure:
            return {'ok': False, 'reason': f'earlier receipts are not yet durable: {failure[1]}', 'since': failure[0]}
        return self._probe_store(root)

    def _probe_store(self, root: Path, budget: float = 2.0) -> dict[str, Any]:
        """One bounded write probe (U9 A05/FP-08): a hung device never blocks the caller.

        At most one probe is outstanding; while it hangs, callers get "not responding" at once
        instead of stacking more blocked probes on the device.
        """
        with self._persist_lock:
            outstanding = getattr(self, '_store_probe', None)
            if outstanding is not None and not outstanding['done'].is_set():
                return {'ok': False, 'reason': f'storage not responding: a probe has waited {time.time() - outstanding["at"]:.0f} s'}
            state = {'done': threading.Event(), 'at': time.time(), 'error': None}
            self._store_probe = state

        def probe() -> None:
            try:
                root.mkdir(parents=True, exist_ok=True, mode=0o700)
                target = root / f'.health.{os.getpid()}.{threading.get_ident()}'
                target.write_bytes(b'ok')
                target.unlink()
            except OSError as exc:
                state['error'] = exc
            finally:
                state['done'].set()

        threading.Thread(target=probe, name='job-store-probe', daemon=True).start()
        if not state['done'].wait(budget):
            return {'ok': False, 'reason': f'storage not responding within {budget:g} s'}
        if state['error'] is not None:
            return {'ok': False, 'reason': f'receipt directory is not writable: {state["error"]}'}
        return {'ok': True}

    def _restore_reservations_locked(self) -> None:
        """Read original receipts, never infer release from server/PID death."""
        from . import job_history
        root = job_history.directory()
        if root is None:
            raise OSError('Durable resource admission requires a workbench receipt directory')
        root_key = str(root.resolve())
        if self._resource_root_key is not None and self._resource_root_key != root_key:
            raise OSError('Resource receipt root changed; reconcile the previous scope first')
        if self._resource_owner_handle is None:
            try:
                import fcntl
            except ImportError as exc:
                raise OSError('Scoped workbench admission requires POSIX owner locking on this host') from exc
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            handle = (root / '.resource-owner.lock').open('a+')
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                handle.close()
                raise OSError('Another JobStore owns resource admission for this receipt root')
            self._resource_owner_handle = handle
            self._resource_root_key = root_key
        if self._restored_root == root_key:
            self._auto_reconcile_retained_locked()
            return
        if self._restored_root is not None:
            raise OSError('Resource receipt root changed; reconcile the previous scope first')
        restored = []
        for path in root.glob('*.json'):
            try:
                row = json.loads(path.read_text())
                if not isinstance(row, dict) or not isinstance(row.get('id'), str):
                    raise ValueError('invalid receipt shape')
                keys = row.get('resourceKeys')
                disposition = row.get('resourceDisposition')
                historical_verify_params = None
                if _native_not_dispatched(row):
                    continue
                if row.get('actionId') == 'corpus.cross-place' and not (_bound_clearance(row) or _cross_place_not_dispatched(row)):
                    from agentdecompile_recovery.corpus.cross_place import freeze_parameters
                    if not row.get('executionRoot'):
                        raise ValueError('historical cross-place has no original execution root')
                    historical_verify_params = freeze_parameters(row.get('params') or {}, Path(row['executionRoot']))
                    expected_action = action_by_id('corpus.cross-place')
                    if not keys:
                        keys = _resource_keys(expected_action, historical_verify_params, base=Path(row['executionRoot']))
                    disposition = 'quarantined'
                if row.get('actionId') == 'recover.verify-package' and not _bound_clearance(row):
                    # An old unguarded exit is not compiler-session clearance.
                    # Recover the deterministic output claim, including terminal
                    # rows that predate resourceKeys. Ambiguous history blocks
                    # admission rather than guessing a different execution root.
                    from agentdecompile_recovery.native_verify_contract import freeze_paths
                    original_root = row.get('executionRoot')
                    if not original_root:
                        raise ValueError('historical native verification has no original execution root')
                    historical_params = row.get('params') or {}
                    if not historical_params.get('out-dir'):
                        original_package = Path(str(historical_params.get('package') or ''))
                        if not original_package.is_absolute():
                            original_package = Path(original_root) / original_package
                        if not (original_package.is_dir() or original_package.is_file()):
                            raise ValueError('historical native verification default output is ambiguous: package no longer exists')
                    historical_verify_params = freeze_paths(historical_params, Path(original_root))
                    if not keys:
                        keys = {'external': [['output', historical_verify_params['out-dir']]]}
                    disposition = 'quarantined'
                if disposition not in {None, 'unreserved', 'held', 'quarantined', 'released'}:
                    raise ValueError('invalid resource disposition')
                if keys is not None and (not isinstance(keys, dict) or any(key not in {'identity', 'pair', 'ghidra', 'external'} for key in keys)):
                    raise ValueError('invalid resource keys')
                if keys:
                    for kind, value in keys.items():
                        if kind == 'pair':
                            if not isinstance(value, list) or len(value) != 2 or any(not isinstance(item, str) or not item for item in value):
                                raise ValueError('invalid pair resource identity')
                        elif kind == 'external':
                            if (not isinstance(value, list) or not value
                                    or any(not isinstance(item, list) or len(item) != 2
                                           or not all(isinstance(part, str) and part for part in item)
                                           for item in value)):
                                raise ValueError('invalid external resource identity')
                            if any(item[0] not in _EXTERNAL_RESOURCE_KINDS or not Path(item[1]).is_absolute() or _canonical_resource_path(item[1], base=Path('/')) != item[1] for item in value):
                                raise ValueError('noncanonical or unknown external resource identity')
                        elif not isinstance(value, str) or not value:
                            raise ValueError('invalid resource identity')
                        path_key = value[0] if kind == 'pair' else value if kind == 'identity' else None
                        if path_key is not None and (not Path(path_key).is_absolute() or _canonical_resource_path(path_key, base=Path('/')) != path_key):
                            raise ValueError('noncanonical database resource identity')
                if disposition in {'held', 'quarantined'} and not keys:
                    raise ValueError('reserved receipt has no resource keys')
                if disposition == 'released':
                    if not (keys or {}).get('external'):
                        continue
                    release_report = self._reconciliation_report_locked(row['id'])
                    if release_report.get('eligible') and release_report.get('reconciliationKind') != 'cross-place-generation':
                        continue
                    # Unknown/mismatched external release receipts cannot drop a claim.
                    disposition = 'quarantined'
                unresolved = disposition in {'held', 'quarantined'} or row.get('status') in {'running', 'cancelling', 'interrupted'} or _ownership_unresolved(row.get('log') or '')
                if not unresolved:
                    continue
                prior_action = action_by_id(row.get('actionId', ''))
                if prior_action is None and not keys:
                    raise ValueError('unknown interrupted action has no recoverable resource identity')
                expected = _resource_keys(prior_action, historical_verify_params or row.get('params') or {}, base=Path(row.get('executionRoot') or root_key))
                if keys is None or not keys:
                    keys = expected
                elif any(keys.get(kind) != value for kind, value in expected.items()):
                    raise ValueError('retained resource identity disagrees with action requirements')
                if not isinstance(keys, dict):
                    raise ValueError('invalid resource keys')
                restored.append((row['id'], keys))
            except (OSError, ValueError, TypeError) as exc:
                raise OSError(f'Cannot reconcile resource receipt {path.name}: {exc}') from exc
        # Validate the whole set before changing any map; duplicate receipts
        # must not silently overwrite an earlier owner.
        seen = set()
        external_seen = []
        for owner, keys in restored:
            for kind, value in keys.items():
                if kind == "external":
                    for claim in value:
                        if any(other != owner and _paths_overlap(claim[1], prior[1]) for other, prior in external_seen):
                            raise OSError("Ambiguous overlapping retained external owners")
                        external_seen.append((owner, claim))
                else:
                    key = (kind, tuple(value) if isinstance(value, list) else value)
                    if key in seen:
                        raise OSError("Ambiguous duplicate retained resource owners")
                    seen.add(key)
        identities = {keys['identity'] for _, keys in restored if keys.get('identity')}
        if any(keys.get('pair') and keys['pair'][0] in identities for _, keys in restored):
            raise OSError("Ambiguous retained database and pair owners")
        for owner, keys in restored:
            if keys.get('identity'):
                self._identity_held[str(keys['identity'])] = owner
            if keys.get('pair'):
                pair = keys['pair']
                if not isinstance(pair, list) or len(pair) != 2:
                    raise OSError('Invalid retained pair reservation')
                self._pair_held[tuple(pair)] = owner
            if keys.get('ghidra'):
                self._ghidra_held[str(keys['ghidra'])] = owner
            for claim in keys.get('external', []):
                self._external_held[tuple(claim)] = owner
        self._restored_root = root_key

    def _cross_place_reconciliation_report_locked(self, row: dict, current: JobRecord | None) -> dict[str, Any]:
        """Structural eligibility only; explicit repair must freshly observe ownership."""
        missing = []
        issue = _cross_place_reconciliation_scope(row)
        if issue: missing.append(issue)
        if type(row.get('receiptVersion')) is not int or row['receiptVersion'] < 1:
            missing.append('valid_receipt_generation')
        if current is not None:
            if row['id'] in self._cross_active or (not current.history_only and current.status in {'queued', 'running', 'cancelling'}):
                missing.append('live_executor_terminal')
            expected = current.to_dict()
            if any(expected.get(k) != row.get(k) for k in
                   ('actionId', 'params', 'argv', 'executionAttempt', 'executionRoot', 'resourceKeys')):
                missing.append('current_reservation_matches_receipt')
        undispatched_generation = row.get('crossPlaceGeneration')
        undispatched = _cross_place_not_dispatched(row)
        if (not undispatched and not missing and current is not None and not current.history_only
                and self.executor is None and _cross_place_not_dispatched(current.to_dict())):
            undispatched = True
            undispatched_generation = current.cross_place_generation
        owner = row.get('executionOwner') or {}
        # A failed owner receipt may still have a trusted in-process observation.
        # Do not borrow an identity from another attempt or a historical handle.
        if not owner and current is not None and not current.history_only and self.executor is None and not missing:
            owner = current.execution_owner
        if undispatched:
            prior = (undispatched_generation or {}).get('priorClearance')
            owner = prior.get('executionOwner') if prior else None
        if not undispatched and (not isinstance(owner, dict) or type(owner.get('pid')) is not int
                or owner['pid'] <= 0 or not owner.get('start_ticks') or not owner.get('boot_id')
                or owner.get('identity_unavailable')):
            missing.append('observed_generation_owner')
        return {'jobId': row['id'], 'ok': True, 'eligible': not missing,
                'reconciliationKind': 'cross-place-generation',
                'scope': 'explicit terminalization of retained guarded generation',
                'missingEvidence': missing, 'receiptVersion': row.get('receiptVersion'),
                'resourceKeys': row.get('resourceKeys'),
                'resourceDisposition': current.resource_disposition if current else row.get('resourceDisposition'),
                'undispatched': undispatched, 'undispatchedGeneration': undispatched_generation if undispatched else None,
                'ownerToObserve': owner,
                'nextAction': 'observe_and_terminalize_generation' if not missing else 'retain_reservation',
                'limitations': ['Eligibility is not session clearance', 'No automatic successor or checkpoint reset']}

    def _repair_cross_place_locked(self, row: dict, report: dict, *, trigger: str) -> dict[str, Any]:
        from . import job_history
        from agentdecompile_recovery.corpus.supervision import save_state, session_clearance
        if trigger != 'catalog_action':
            return {**report, 'eligible': False, 'nextAction': 'retain_reservation',
                    'missingEvidence': ['explicit_generation_reconciliation']}
        owner = report.get('ownerToObserve')
        if owner and session_clearance(owner) != 'clear':
            return {**report, 'eligible': False, 'nextAction': 'retain_reservation',
                    'missingEvidence': ['fresh_whole_session_clearance']}
        job_id = row['id']
        # On restoration the original holder may be gone. Acquire the same
        # physical lock before repairing, rather than declaring release while
        # an independent cooperating writer owns this output.
        if not _cross_place_preparing(row) or job_id in self._cross_leases:
            from agentdecompile_recovery.corpus.cross_place_admission import _held_descriptor
            import fcntl
            area = Path(row['params']['out-dir']) / '.cross-place'
            descriptor = self._cross_leases.get(job_id)
            opened = descriptor is None
            try:
                if opened:
                    descriptor = os.open(area / '.owner.lock', os.O_RDWR | os.O_NOFOLLOW)
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                _held_descriptor(descriptor, area)
                issue = _cross_place_reconciliation_scope(row)
                if issue: raise ValueError(issue)
            except (OSError, ValueError) as exc:
                if opened and descriptor is not None: os.close(descriptor)
                return {**report, 'eligible': False, 'nextAction': 'retain_reservation',
                        'missingEvidence': ['exclusive_physical_output_lease'], 'error': str(exc)}
            self._cross_leases[job_id] = descriptor
        root = job_history.directory()
        path = root / (job_id + '.json')
        current = self._jobs.get(job_id)
        original = json.loads(path.read_text())
        if original != row:
            return {**report, 'eligible': False, 'nextAction': 'retain_reservation', 'error': 'Receipt changed during observation'}
        terminal = dict(row)
        if report['undispatched']:
            terminal['crossPlaceGeneration'] = report['undispatchedGeneration']
        if not report['undispatched']:
            terminal['executionOwner'] = dict(owner)
            terminal['clearanceObservation'] = {
                'source': 'local-executor-session-observer-v1', 'jobId': job_id,
                'attempt': row['executionAttempt'], 'resourceKeys': row['resourceKeys'],
                'argvDigest': hashlib.sha256(json.dumps(row['argv'], separators=(',', ':')).encode()).hexdigest(),
                'process': dict(owner), 'sessionClearance': 'clear', 'observedAt': time.time()}
            terminal['crossPlaceGeneration'] = {**row['crossPlaceGeneration'], 'phase': 'cleared'}
        terminal.update(status='cancelled' if report['undispatched'] else 'failed',
                        resourceDisposition='released', finishedAt=time.time(),
                        error='Retained generation reconciled; explicit continuation is required.',
                        receiptVersion=max(row['receiptVersion'], self._receipt_versions.get(job_id, 0)) + 1)
        terminal['resourceReconciliation'] = {'trigger': trigger, 'at': time.time(),
            'basisReceiptVersion': row['receiptVersion'],
            'operation': 'terminalize_undispatched_generation' if report['undispatched'] else 'terminalize_observed_clear_generation'}
        # The held duplicate and every resource map remain intact if this fails.
        with self._persist_lock:
            save_state(path, terminal)
            self._receipt_versions[job_id] = terminal['receiptVersion']
        if current is not None:
            current.status = terminal['status']
            current.finished_at = terminal['finishedAt']
            current.error = terminal['error']
            current.execution_owner = dict(terminal.get('executionOwner') or {})
            current.clearance_observation = dict(terminal.get('clearanceObservation') or {})
            current.cross_place_generation = dict(terminal['crossPlaceGeneration'])
            current.resource_disposition = 'released'
        self._close_cross_lease_locked(job_id)
        keys = terminal['resourceKeys']
        for mapping, key in [(self._identity_held, keys.get('identity')),
                             (self._pair_held, tuple(keys['pair']) if keys.get('pair') else None),
                             (self._ghidra_held, keys.get('ghidra')),
                             *[(self._external_held, tuple(claim)) for claim in keys.get('external', [])]]:
            if key is not None and mapping.get(key) == job_id: del mapping[key]
        return {**report, 'released': True, 'resourceDisposition': 'released',
                'receiptVersion': terminal['receiptVersion'], 'nextAction': 'reservation_repaired'}

    def _reconciliation_report_locked(self, job_id: str) -> dict[str, Any]:
        from . import job_history
        result = {'jobId': job_id, 'ok': False, 'eligible': False,
                  'nextAction': 'retain_reservation', 'missingEvidence': [],
                  'scope': 'repair stale reservation from committed terminal local receipt',
                  'limitations': ['No remote operation reconciliation', 'No detached-child or external-writer proof']}
        if not re.fullmatch(r'[a-f0-9]{12,32}', job_id):
            return {**result, 'error': 'Invalid job identity'}
        root = job_history.directory()
        try:
            if root is None:
                raise OSError('Receipt store unavailable')
            row = json.loads((root / (job_id + '.json')).read_text())
            if not isinstance(row, dict) or row.get('id') != job_id:
                raise ValueError('Receipt identity mismatch')
        except (OSError, ValueError) as exc:
            return {**result, 'error': str(exc), 'missingEvidence': ['durable_job_receipt']}
        current = self._jobs.get(job_id)
        if row.get('actionId') == 'corpus.cross-place' and row.get('crossPlaceGeneration'):
            committed_release = (row.get('resourceDisposition') == 'released'
                and row.get('status') in {'ok', 'failed', 'cancelled'} and row.get('finishedAt')
                and (_bound_clearance(row) or _cross_place_not_dispatched(row)))
            if not committed_release or job_id in self._cross_leases:
                return self._cross_place_reconciliation_report_locked(row, current)
        keys, proof, owner = row.get('resourceKeys'), row.get('clearanceObservation'), row.get('executionOwner')
        missing = []
        if type(row.get('receiptVersion')) is not int or row['receiptVersion'] < 1:
            missing.append('valid_receipt_generation')
        if row.get('actionId') not in LOCAL_RECONCILIATION_ACTIONS | _EXTERNAL_ACTION_CONTRACTS.keys():
            missing.append('qualified_provider_lifecycle_contract')
        if isinstance(keys, dict) and keys.get('external') and not _external_contract_matches(row.get('actionId'), row.get('params') or {}, keys, Path(row.get('executionRoot') or '/')):
            missing.append('qualified_external_resource_contract')
        if row.get('actionId') == 'recover.verify-package' and not _bound_clearance(row):
            missing.append('qualified_native_guarded_execution')
        if row.get('resourceDisposition') != 'released' or row.get('status') not in {'ok', 'failed', 'cancelled'} or not row.get('finishedAt'):
            missing.append('committed_terminal_release')
        if not isinstance(keys, dict) or not keys:
            missing.append('recorded_resource_identity')
        if _cross_place_not_dispatched(row):
            pass  # Explicit durable intent proves this generation never dispatched.
        elif not isinstance(proof, dict) or not isinstance(owner, dict) or not owner:
            missing.append('trusted_local_executor_clearance')
        else:
            expected_argv = hashlib.sha256(json.dumps(row.get('argv'), separators=(',', ':')).encode()).hexdigest()
            expected = {'jobId': job_id, 'attempt': row.get('executionAttempt'), 'resourceKeys': keys,
                        'argvDigest': expected_argv, 'process': owner}
            if not row.get('executionAttempt') or any(proof.get(key) != value for key, value in expected.items()):
                missing.append('same_attempt_resource_and_execution_binding')
            if proof.get('source') != 'local-executor-session-observer-v1' or proof.get('sessionClearance') != 'clear':
                missing.append('qualified_local_clearance_observation')
            observed = proof.get('observedAt')
            finished = row.get('finishedAt')
            try:
                valid_times = type(observed) in (int, float) and math.isfinite(observed) and observed > 0 and type(finished) in (int, float) and math.isfinite(finished) and observed <= finished
            except OverflowError:
                valid_times = False
            if not valid_times:
                missing.append('clearance_before_full_action_completion')
            if not owner.get('start_ticks') or not owner.get('boot_id') or type(owner.get('pid')) is not int:
                missing.append('stable_execution_owner')
        if current is not None:
            if current.status not in {'ok', 'failed', 'cancelled'}:
                missing.append('live_executor_terminal')
            if current.action_id != row.get('actionId') or current.execution_attempt != row.get('executionAttempt') or current.resource_keys != keys or current.argv != row.get('argv'):
                missing.append('current_reservation_matches_receipt')
            if self._receipt_versions.get(job_id) != row.get('receiptVersion'):
                missing.append('current_receipt_generation')
        result.update(ok=True, eligible=not missing, missingEvidence=missing,
                      resourceDisposition=current.resource_disposition if current else row.get('resourceDisposition'),
                      resourceKeys=keys, receiptVersion=row.get('receiptVersion'),
                      nextAction='repair_stale_reservation' if not missing else 'retain_reservation')
        return result

    def reconciliation_report(self, job_id: str) -> dict[str, Any]:
        """Read-only: no owner lock acquisition, writes, process probes or release."""
        with self._lock:
            return self._reconciliation_report_locked(job_id)

    def _repair_retained_locked(self, job_id: str, *, trigger: str) -> dict[str, Any]:
        from . import job_history
        from agentdecompile_recovery.corpus.supervision import save_state
        report = self._reconciliation_report_locked(job_id)
        if not report.get('eligible'):
            return report
        root = job_history.directory()
        path = root / (job_id + '.json')
        row = json.loads(path.read_text())
        # The receipt-root authority excludes another scoped executor; compare
        # generation again before recording the decision and releasing maps.
        if row.get('receiptVersion') != report['receiptVersion']:
            return {**report, 'eligible': False, 'nextAction': 'retain_reservation', 'error': 'Receipt changed during reconciliation'}
        if report.get('reconciliationKind') == 'cross-place-generation':
            return self._repair_cross_place_locked(row, report, trigger=trigger)
        row['resourceReconciliation'] = {'trigger': trigger, 'at': time.time(),
                                         'basisReceiptVersion': row.get('receiptVersion'),
                                         'operation': 'repair_committed_terminal_release'}
        with self._persist_lock:
            save_state(path, row)
        current = self._jobs.get(job_id)
        if current is not None:
            current.resource_disposition = 'released'
        self._close_cross_lease_locked(job_id)
        keys = report['resourceKeys']
        releases = [(self._identity_held, keys.get('identity')),
                    (self._pair_held, tuple(keys['pair']) if keys.get('pair') else None),
                    (self._ghidra_held, keys.get('ghidra'))]
        releases.extend((self._external_held, tuple(claim)) for claim in keys.get('external', []))
        for mapping, key in releases:
            if key is not None and mapping.get(key) == job_id:
                del mapping[key]
        return {**report, 'released': True, 'nextAction': 'reservation_repaired'}

    def _auto_reconcile_retained_locked(self) -> None:
        owners = (set(self._identity_held.values()) | set(self._pair_held.values())
                  | set(self._ghidra_held.values()) | set(self._external_held.values()))
        for owner in owners:
            job = self._jobs.get(owner)
            if job is not None and job.resource_disposition == 'quarantined':
                self._repair_retained_locked(owner, trigger='scoped_admission')

    def reconcile_resources(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            self._restore_reservations_locked()
            return self._repair_retained_locked(job_id, trigger='catalog_action')

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
        mcp_reserve: Callable[[str], Any] | None = None,
        preparation_authority: Any = None,
        _execution_root: Path | None = None,
    ) -> JobRecord:
        job = JobRecord(
            id=uuid.uuid4().hex[:12],
            action_id=action.id,
            title=action.title,
            argv=list(argv),
            params=dict(params),
            execution_root=str(preparation_authority.root if preparation_authority is not None else _execution_root if _execution_root is not None else (live_root() or Path.cwd()).resolve()),
            trusted_preparation_facts_inventory=trusted_preparation_facts_inventory,
            trusted_preparation_probe=trusted_preparation_probe,
            mcp_reserve=mcp_reserve,
            preparation_authority=preparation_authority,
        )
        if preparation_authority is not None:
            preparation_authority.root_start('allocated', job.id)
        cancel = threading.Event()
        with self._lock:
            _observe_native_no_dispatch(job)
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
        if preparation_authority is not None:
            preparation_authority.root_start('attempted', job.id)
        thread.start()
        return self.get(job.id) or _copy_job(job)

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
            native_pending = _native_not_dispatched(job.to_dict())
            if job.status in {"queued", "running"}:
                job.status = "cancelling"
            if native_pending:
                _observe_native_no_dispatch(job)
            if event is not None:
                event.set()
            self._persist_locked(job, force=True)
            return _copy_job(job)

    def _run(self, job_id: str, cancel: threading.Event) -> None:
        # Authority exists only on the internal live record; copies/history omit it.
        authority = self._jobs[job_id].preparation_authority
        try:
            if authority is not None:
                authority.root_start('entered', job_id)
            self._run_body(job_id, cancel)
        finally:
            if authority is not None:
                authority.root_start('finished', job_id)

    def _run_body(self, job_id: str, cancel: threading.Event) -> None:
        identity_key = ""
        pair_entry: tuple[str, str] | None = None
        ghidra_key = ""
        external_entries: tuple[tuple[str, str], ...] = ()
        worker_acquired = False
        cross_owner = None
        action = action_by_id(self._jobs[job_id].action_id)
        if _read_only_supervisor_status(self._jobs[job_id].action_id, self._jobs[job_id].params):
            action = None  # inspection must remain available under quarantine
        job = self._jobs[job_id]
        cwd = Path(job.execution_root) if job.execution_root else (live_root() or Path.cwd()).resolve()
        job.execution_root = str(cwd)
        try:
            if job.action_id in {"recover.verify-package", "corpus.cross-place"}:
                if job.action_id == "recover.verify-package":
                    from agentdecompile_recovery.native_verify_contract import freeze_parameters, guarded_command
                else:
                    from agentdecompile_recovery.corpus.cross_place import freeze_parameters, guarded_command
                frozen_params = freeze_parameters(dict(job.params), cwd)
                frozen_argv = guarded_command(frozen_params)
                frozen_keys = _resource_keys(action, frozen_params, base=cwd)
                # cancel() must never observe frozen argv/params paired with
                # an obsolete predispatch binding, including resource waiters.
                with self._lock:
                    job.params, job.argv = frozen_params, frozen_argv
                    _observe_native_no_dispatch(job)
                    self._persist_locked(job, force=True)
            else:
                # Pin snapshot arguments to their reserved physical paths;
                # subprocess argparse does not expand a shell-style ~/out.
                for _kind, name in _EXTERNAL_ACTION_CONTRACTS.get(job.action_id, ()):
                    destination = _canonical_resource_path(job.params.get(name), base=cwd)
                    if destination is None:
                        raise ValueError(f"{job.action_id} requires resource parameter {name}")
                    job.params[name] = destination
                if job.action_id in _EXTERNAL_ACTION_CONTRACTS:
                    job.argv = build_command(action, job.params)
                frozen_keys = _resource_keys(action, job.params, base=cwd)
            with self._lock:
                if frozen_keys:
                    self._restore_reservations_locked()
        except (OSError, ValueError) as exc:
            with self._lock:
                job = self._jobs[job_id]
                job.status, job.error, job.finished_at = 'failed', str(exc), time.time()
                if job.action_id in {'review.list', 'review.decide'}:
                    from ...match_review import ReviewError
                    job.log = json.dumps(exc.result() if isinstance(exc, ReviewError) else {'ok': False, 'error': 'unavailable', 'refreshRequired': False})
                _observe_native_no_dispatch(job)
                self._persist_locked(job, force=True)
            return
        while True:
            with self._lock:
                if cancel.is_set():
                    job = self._jobs[job_id]
                    job.status = "cancelled"
                    job.finished_at = time.time()
                    _observe_native_no_dispatch(job)
                    self._persist_locked(job, force=True)
                    return
                job = self._jobs[job_id]
                coordinator = job.action_id in {"workbench.prepare", "workbench.workflow-control", "workbench.activity-snapshot", "workbench.resource-reconciliation-report", "workbench.resource-reconcile"}
                # Coordinators do not consume a worker slot below, so requiring a
                # free one here only starved them: with MAX_CONCURRENT real jobs
                # running, a Pause (workbench.workflow-control) could never reach
                # its ownership checks and spun in this admission loop instead of
                # taking effect.  Full worker capacity must not block Pause.  The
                # identity/pair/Ghidra locks below still apply unchanged.
                can_run = coordinator or self._running < MAX_CONCURRENT
                scope = action.identity_scope if action is not None else ""
                if can_run and scope:
                    identity_key = identity_lock_key(job.params) or ""
                    if scope == "database":
                        holder = self._identity_held.get(identity_key)
                        if identity_key and (
                            (holder and holder != job_id)
                            or any(db == identity_key and owner != job_id for (db, _pair), owner in self._pair_held.items())
                        ):
                            can_run = False
                    elif scope == "pair":
                        pair_key = match_pair_lock_key(job.params) or ""
                        pair_entry = (identity_key, pair_key) if identity_key and pair_key else None
                        holder = self._identity_held.get(identity_key)
                        pair_holder = self._pair_held.get(pair_entry) if pair_entry else None
                        if (holder and holder != job_id) or (pair_holder and pair_holder != job_id):
                            can_run = False
                mutates_ghidra = bool(action and action.ghidra_exclusive) or (action is not None and action.backend == "mcp-cli" and action.mutating)
                if can_run and mutates_ghidra:
                    ghidra_key = ghidra_lock_key(job.params)
                    holder = self._ghidra_held.get(ghidra_key)
                    if ghidra_key and holder and holder != job_id:
                        can_run = False
                external_entries = tuple(tuple(claim) for claim in frozen_keys.get("external", []))
                if can_run and any(owner != job_id and _paths_overlap(entry[1], held[1]) for entry in external_entries for held, owner in self._external_held.items()):
                    can_run = False
                if can_run and not coordinator:
                    # Resource admission with aging reservations (U9 A15/A16): wait, never refuse, here.
                    from agentdecompile_recovery.corpus.dashboard import resource_admission as _ra
                    if _ra.gate_enabled():
                        admitted, why, _holder = _ra.runtime_admit(
                            job_id, job.action_id,
                            running=[j.action_id for j in self._jobs.values() if j.status == "running"],
                            queued=[(j.id, j.action_id, j.created_at) for j in self._jobs.values() if j.status == "queued"])
                        if not admitted:
                            can_run = False
                            if job.admission_wait != why:
                                job.admission_wait = why
                                self._persist_locked(job, force=True)
                        else:
                            job.admission_wait = ""
                if can_run:
                    # Coordinators wait on and schedule child jobs; they do
                    # not themselves consume a worker slot. Counting them
                    # here but deliberately not decrementing them in finally
                    # permanently exhausted MAX_CONCURRENT after four
                    # preparation runs, leaving every real MCP job queued.
                    if not coordinator:
                        self._running += 1
                        worker_acquired = True
                    if identity_key and scope == "database":
                        self._identity_held[identity_key] = job_id
                    if pair_entry and scope == "pair":
                        self._pair_held[pair_entry] = job_id
                    if ghidra_key:
                        self._ghidra_held[ghidra_key] = job_id
                    for entry in external_entries:
                        self._external_held[entry] = job_id
                    job.resource_keys = frozen_keys
                    job.resource_disposition = "held" if job.resource_keys else "unreserved"
                    # Persist invalidation synchronously with held intent, before
                    # any injected or default executor can possibly be invoked.
                    job.no_dispatch_observation = {}
                    job.status = "running"
                    job.started_at = time.time()
                    try:
                        self._persist_locked(job, force=True)
                    except Exception as exc:  # noqa: BLE001 — admission must never leak
                        job.error = str(exc)
                        job.status = "failed"
                        job.finished_at = time.time()
                        job.resource_disposition = "released"
                        self._release_admission_locked(job_id, identity_key, pair_entry, ghidra_key, external_entries, worker_acquired)
                        return
                    argv = list(job.argv)
                    break
            time.sleep(POLL_S)
        try:
            def wait_for_owner(proc: subprocess.Popen[str], output: str) -> None:
                self._wait_for_process_owner(job_id, proc, output)

            if action is not None and action.backend == "preparation":
                from agentdecompile_recovery.corpus.dashboard import preparation
                try:
                    code, log = preparation.execute(dict(job.params), cancel, authority=job.preparation_authority)
                except preparation._PreparationIssuanceWait as exc:
                    code, log = 1, json.dumps(preparation.authority_refusal(exc)[0])
                except preparation._PreparationControlWait as exc:
                    code, log = 1, json.dumps(preparation.authority_refusal(exc)[0])
                except preparation._PreparationAuthorityRefused as exc:
                    code, log = 1, json.dumps(preparation.authority_refusal(exc)[0])
            elif action is not None and action.backend == "match-review":
                from .match_review import execute
                code, log = execute(dict(job.params), cancel, decide=action.command == 'decide')
            elif action is not None and action.backend == "merge-evidence":
                from agentdecompile_recovery.corpus.dashboard.workflow import merge_evidence
                code, log = 0, json.dumps(merge_evidence(str(job.params["db"]), str(job.params["run"])))
            elif action is not None and action.backend == "workflow-control":
                from agentdecompile_recovery.corpus.dashboard import preparation
                try:
                    code, log = 0, json.dumps(preparation.control(dict(job.params)))
                except preparation._PreparationIssuanceWait as exc:
                    code, log = 1, json.dumps(preparation.authority_refusal(exc)[0])
                except preparation._PreparationControlWait as exc:
                    code, log = 1, json.dumps(preparation.authority_refusal(exc)[0])
                except preparation._PreparationAuthorityRefused as exc:
                    code, log = 1, json.dumps(preparation.authority_refusal(exc)[0])
            elif action is not None and action.backend == "activity-snapshot":
                from agentdecompile_recovery.corpus.dashboard.entity_activity import snapshot
                code, log = 0, json.dumps(snapshot(locator=job.params.get("locator", ""), slug=job.params.get("slug", ""), program=job.params.get("program", "") or job.params.get("programPath", "")))
            elif action is not None and action.backend == "resource-reconciliation-report":
                result = self.reconciliation_report(str(job.params['job_id']))
                code, log = (0 if result.get('ok') else 1), json.dumps(result)
            elif action is not None and action.backend == "resource-reconcile":
                result = self.reconcile_resources(str(job.params['job_id']))
                code, log = (0 if result.get('released') else 1), json.dumps(result)
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
                    on_unresolved=wait_for_owner,
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
                        on_unresolved=wait_for_owner,
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
                    unresolved = _ownership_unresolved(output)
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
                    mcp_reserve=job.mcp_reserve,
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
                    def observe_owner(identity: dict) -> None:
                        with self._lock:
                            job.execution_owner = dict(identity)
                            self._persist_locked(job, force=True)
                    def observe_clearance(identity: dict) -> None:
                        with self._lock:
                            job.clearance_observation = {
                                'source': 'local-executor-session-observer-v1', 'jobId': job.id,
                                'attempt': job.execution_attempt, 'resourceKeys': dict(job.resource_keys),
                                'argvDigest': hashlib.sha256(json.dumps(job.argv, separators=(',', ':')).encode()).hexdigest(),
                                'process': dict(identity), 'sessionClearance': 'clear', 'observedAt': time.time(),
                            }
                            self._persist_locked(job, force=True)
                    if job.action_id == 'corpus.cross-place':
                        from agentdecompile_recovery.corpus import cross_place, cross_place_admission
                        with self._lock:
                            self._cross_active.add(job.id)
                            job.cross_place_generation = {'version': 1, 'phase': 'preparing',
                                'binding': _cross_place_preparation_binding(job.to_dict())}
                            self._persist_locked(job, force=True)
                        lease = cross_place_admission.output_owner(job.params['out-dir'],
                            [Path(job.params['db']), Path(job.params['raw-dir']), Path(job.params['byteexact-receipt'])])
                        lease.__enter__()
                        cross_owner = lease
                        # The worker thread borrows via output_owner; the store
                        # retains a separate descriptor that can close on any
                        # reconciliation thread without touching threadlocals.
                        self._cross_leases[job.id] = os.dup(cross_place_admission.lease_fds()[0])
                        def transition(phase, command, envelope):
                            with self._lock:
                                if phase == 'intent':
                                    prior = job.to_dict(include_log=False)
                                    prior['argv'] = list(job.argv)
                                    preparing = _cross_place_preparing(prior)
                                    prior.pop('crossPlaceGeneration', None)
                                    if job.cross_place_generation and not preparing and not _bound_clearance(prior):
                                        raise ValueError('successor_requires_bound_session_clearance')
                                    job.execution_attempt = envelope['generation']
                                    job.argv = list(command)
                                    job.execution_owner = {}
                                    job.clearance_observation = {}
                                    job.cross_place_generation = {'version': 1, 'phase': 'intent',
                                        'generation': envelope['generation'], 'envelope': envelope,
                                        'priorClearance': prior if prior.get('executionOwner') else None}
                                elif phase == 'undispatched':
                                    job.cross_place_generation['phase'] = 'undispatched'
                                elif phase == 'dispatch':
                                    if cancel.is_set():
                                        job.cross_place_generation['phase'] = 'undispatched'
                                        self._persist_locked(job, force=True)
                                        raise InterruptedError('cancelled before generation dispatch')
                                    job.cross_place_generation['phase'] = 'dispatch-possible'
                                elif phase == 'cleared':
                                    if _cross_place_not_dispatched(job.to_dict()):
                                        return  # Explicit no-spawn observation, not session clearance.
                                    if not _bound_clearance(job.to_dict()):
                                        raise ValueError('ownership remains unresolved: generation session')
                                    job.cross_place_generation['phase'] = 'cleared'
                                self._persist_locked(job, force=True)
                        def execute_generation(command, fds, event):
                            def not_started():
                                with self._lock:
                                    if job.execution_owner:
                                        raise ValueError('undispatched_generation_has_owner')
                                    job.cross_place_generation['phase'] = 'undispatched'
                                    self._persist_locked(job, force=True)
                            return _default_executor(command, cwd, event, on_output=publish_log,
                                on_started=observe_owner, on_unresolved=wait_for_owner, on_clearance=observe_clearance,
                                inherited_fds=fds, on_not_started=not_started)
                        code, log = cross_place.supervise(job.params, execute=execute_generation,
                            transition=transition, cancel=cancel)
                    else:
                        code, log = _default_executor(
                            argv, cwd, cancel, on_output=publish_log,
                            unlimited=unlimited_match, on_started=observe_owner,
                            on_unresolved=wait_for_owner,
                            on_peak=_record_peak(job.action_id),
                            checkpointed=bool(action is not None and action.long_running),
                            on_clearance=observe_clearance if job.action_id in LOCAL_RECONCILIATION_ACTIONS | _EXTERNAL_ACTION_CONTRACTS.keys() else None,
                        )
                if action is not None and action.backend == "bsim-cli":
                    from agentdecompile_recovery.corpus.bsim_ops import _bsim_cli_error
                    if _bsim_cli_error(log, ""):
                        code = code or 1
            with self._lock:
                job = self._jobs[job_id]
                # Audited snapshot and exact guarded native-verifier commands
                # can release after bound session clearance. Other compiler,
                # Wine and provider profiles remain unqualified.
                has_external_claims = bool(job.resource_keys.get("external")) and job.action_id != "review.decide"
                job.resource_disposition = ("quarantined" if (has_external_claims and not (self.executor is None and _external_contract_matches(job.action_id, job.params, job.resource_keys, cwd) and (_bound_clearance(job.to_dict()) or _cross_place_not_dispatched(job.to_dict())))) or _ownership_unresolved(log)
                                            else "released") if job.resource_keys else "unreserved"
                job.log = log[-MAX_LOG_BYTES:]
                job.returncode = code
                job.finished_at = time.time()
                # This executor is returning. A quarantined session may still
                # own resources, but it is no longer an active catalog worker.
                if cancel.is_set() and job.status != "cancelled" and not (job.action_id == "review.decide" and code == 0):
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
                if job.resource_keys:
                    job.resource_disposition = "released" if _cross_place_not_dispatched(job.to_dict()) else "quarantined"
                job.status = "cancelled" if cancel.is_set() else "failed"
                job.finished_at = time.time()
        finally:
            # Always unwind the borrow on its originating thread. The duplicate
            # remains held until the terminal receipt commits or reconciliation.
            try:
                if cross_owner is not None:
                    cross_owner.__exit__(None, None, None)
            finally:
                with self._lock:
                    self._cross_active.discard(job_id)
                    job = self._jobs[job_id]
                    if job.status in {"queued", "running", "cancelling"}:
                        # BaseException may bypass the normal terminal projection.
                        # Hand ownership to reconciliation, never leave a dead
                        # runner represented as an active executor.
                        job.status = "cancelled" if cancel.is_set() else "failed"
                        job.finished_at = time.time()
                        job.resource_disposition = "quarantined" if job.resource_keys else "unreserved"
                        job.log_reason = "Executor interrupted; ownership requires resource reconciliation."
                    try:
                        self._persist_locked(job, force=True)
                        if job.resource_disposition not in {'held', 'quarantined'}:
                            self._close_cross_lease_locked(job_id)
                    except BaseException as exc:
                        job.resource_disposition = "quarantined" if job.resource_keys else "unreserved"
                        job.log_reason = f"Terminal receipt not committed; reservation retained: {exc}"
                        if not isinstance(exc, OSError):
                            raise
                    finally:
                        # Capacity tracks this runner's lifetime. The release
                        # helper retains resource maps while held/quarantined;
                        # later reconciliation must not decrement capacity again.
                        self._release_admission_locked(job_id, identity_key, pair_entry, ghidra_key, external_entries, worker_acquired)

    def _close_cross_lease_locked(self, job_id: str) -> None:
        descriptor = self._cross_leases.get(job_id)
        if descriptor is not None:
            os.close(descriptor)  # Never unlock the shared open file description.
            del self._cross_leases[job_id]

    def _wait_for_process_owner(self, job_id: str, proc: subprocess.Popen[str], output: str) -> None:
        """Keep this job's admission until its exact child handle reports exit."""
        with self._lock:
            job = self._jobs[job_id]
            job.resource_disposition = "quarantined"
            job.execution_owner.setdefault("pid", proc.pid)
            job.status = "cancelling"
            job.finished_at = None
            job.log = output[-MAX_LOG_BYTES:]
            job.error = "Worker ownership is unresolved; target admission remains held until process exit is observed."
            self._persist_locked(job, force=True)
        # Reuse the job thread as a monitor. Retain its worker slot as well as
        # target locks; unrelated jobs can still use the remaining capacity.
        # Popen.poll observes this child lifetime, never a newly looked-up PID.
        try:
            while True:
                try:
                    if proc.poll() is not None:
                        break
                except OSError:
                    # A failed observation cannot authorize another writer.
                    pass
                time.sleep(POLL_S)
        except BaseException:
            with self._lock:
                # The executor records a terminal failure on return/unwind.
                # Keep the exact owner and quarantined claims for the existing
                # qualified resource-reconciliation observer; do not adopt a
                # replacement PID or claim that this monitor is still running.
                job.log_reason = "Exact-child monitor interrupted before observed exit; resource reconciliation required."
            raise
        with self._lock:
            # Exact-child exit is necessary, but the executor must still
            # corroborate session clearance before releasing this reservation.
            job.error = ""

    def _release_admission_locked(
        self,
        job_id: str,
        identity_key: str,
        pair_entry: tuple[str, str] | None,
        ghidra_key: str,
        external_entries: tuple[tuple[str, str], ...],
        worker_acquired: bool,
    ) -> None:
        if worker_acquired:
            self._running = max(0, self._running - 1)
        job = self._jobs.get(job_id)
        if job is not None and job.resource_disposition in {"held", "quarantined"}:
            return
        if identity_key and self._identity_held.get(identity_key) == job_id:
            self._identity_held.pop(identity_key, None)
        if pair_entry and self._pair_held.get(pair_entry) == job_id:
            self._pair_held.pop(pair_entry, None)
        if ghidra_key and self._ghidra_held.get(ghidra_key) == job_id:
            self._ghidra_held.pop(ghidra_key, None)
        for entry in external_entries:
            if self._external_held.get(entry) == job_id:
                self._external_held.pop(entry, None)

    def _trim_locked(self) -> None:
        while len(self._order) > MAX_JOBS:
            old = self._order.pop(0)
            job = self._jobs.get(old)
            if job is not None and (job.status in {"queued", "running", "cancelling"} or job.resource_disposition in {"held", "quarantined"}):
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
        resource_disposition=job.resource_disposition, resource_keys=dict(job.resource_keys),
        execution_attempt=job.execution_attempt, execution_root=job.execution_root, execution_owner=dict(job.execution_owner), clearance_observation=dict(job.clearance_observation),
        no_dispatch_observation=dict(job.no_dispatch_observation),
        cross_place_generation=dict(job.cross_place_generation),
        history_only=job.history_only, owner_unavailable=job.owner_unavailable,
        history_source=job.history_source, log_state=job.log_state,
        log_reason=job.log_reason,
        admission_wait=job.admission_wait, log_truncated=job.log_truncated,
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
                     resource_disposition=('quarantined' if payload.get('resourceDisposition') == 'held' else payload.get('resourceDisposition', 'quarantined' if payload.get('ownershipUnresolved') else 'unreserved')), resource_keys=dict(payload.get('resourceKeys') or {}),
                     execution_attempt=payload.get('executionAttempt', ''), execution_root=payload.get('executionRoot', ''), execution_owner=dict(payload.get('executionOwner') or ({'pid': payload['workerPid'], 'identity_unavailable': True} if payload.get('workerPid') is not None else {})), clearance_observation=dict(payload.get('clearanceObservation') or {}),
                     no_dispatch_observation=dict(payload.get('noDispatchObservation') or {}),
                     cross_place_generation=dict(payload.get('crossPlaceGeneration') or {}),
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
        if _ownership_unresolved(log):
            return {'ok': False, 'ownershipResolved': False, 'ownershipUnresolved': True,
                    'error': 'Remote inspection ownership remains unresolved', 'observation': observed}
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
    if _ownership_unresolved(log):
        return {'ok': False, 'ownershipResolved': False, 'ownershipUnresolved': True,
                'error': 'Remote export ownership remains unresolved', 'data': data, 'observation': observed}
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
            result.put({'ok': False, 'error': str(exc), 'ownershipResolved': False, 'ownershipUnresolved': True})
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
    if _ownership_note(value):
        value.update(ok=False, ownershipResolved=False, ownershipUnresolved=True, quarantined=True)
    else:
        value['ownershipResolved'] = True
    return value


def _mcp_executor(
    action: ActionSpec,
    params: dict[str, Any],
    cancel: threading.Event,
    *,
    trusted_preparation_facts_inventory: bool = False,
    trusted_preparation_probe: bool = False,
    mcp_reserve: Callable[[str], Any] | None = None,
) -> tuple[int, str]:
    # Do not hold CONTEXT_LOCK across the loopback MCP HTTP request.  The MCP
    # handler uses the same lock while serving that request; holding it here
    # makes a dashboard job wait forever for its own request to acquire the
    # lock.  Each bridge operation serializes its own session-critical call.
    from .. import mcp_budget
    from ..provider_breaker import breaker_for, is_crash
    breaker, caller = breaker_for("mcp"), uuid.uuid4().hex
    admitted, why = breaker.admit(caller)
    if not admitted:
        # One shared recovery probe per provider (FP-10): waiting tasks do not call a crashed provider.
        return 1, json.dumps({'ok': False, 'error': why, 'provider': 'mcp', 'providerBreaker': breaker.status()})
    try:
        return _mcp_dispatch(action, params, cancel, mcp_budget, mcp_reserve, breaker, caller, is_crash,
                             trusted_preparation_facts_inventory, trusted_preparation_probe)
    finally:
        breaker.release(caller)  # no-op unless this call held the probe and never recorded it


def _mcp_dispatch(action, params, cancel, mcp_budget, mcp_reserve, breaker, caller, is_crash,
                  trusted_preparation_facts_inventory, trusted_preparation_probe):
    with mcp_budget.dispatch_scope(mcp_reserve) as dispatch:
        try:
            with MCP_EXECUTOR_LOCK:
                code, log = _mcp_executor_in_context(
                    action, params, cancel,
                    trusted_preparation_facts_inventory=trusted_preparation_facts_inventory,
                    trusted_preparation_probe=trusted_preparation_probe,
                )
                breaker.record(caller, crashed=bool(code) and is_crash(log))
                if dispatch['unknown']:
                    # A later clear response cannot reconcile an earlier
                    # uncertain provider effect in this execution sequence.
                    return code or 1, log + _ownership_note({'ownershipUnresolved': True})
                return code, log
        except mcp_budget.DispatchRefused as exc:
            unresolved = dispatch['unknown'] or bool(dispatch['dispatched'] and action.mutating)
            return 1, json.dumps({
                'ok': False, 'error': str(exc), **exc.decision,
                **({'ownershipResolved': False, 'ownershipUnresolved': True} if unresolved else {}),
            })


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
            return 1, "Could not open the selected project without analysis.\n" + str(opened.get("error") or opened.get("text")) + _ownership_note(opened)
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
            return 1, f"Could not make {program} current in the selected project.\n{detail}\n" + _ownership_note(ensured)
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
    # then replay only when the response establishes no unresolved effect.
    # An uncertain earlier dispatch must be reconciled, never blindly replayed.
    # Without this recovery a long
    # automatic preparation wave quietly accumulates transient failures until
    # an operator manually restarts it.
    missing_session = "missing session id" in str(hit.get("error") or "").casefold()
    if missing_session and not cancel.is_set() and not _ownership_note(hit):
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
                **({'ownershipResolved': False, 'ownershipUnresolved': True} if _ownership_note(reopened) else {}),
            }
    unknown_ownership = bool(_ownership_note(hit))
    if unknown_ownership:
        hit = {**hit, 'ok': False}
    text = hit.get("text") or ""
    parsed = hit.get("parsed")
    if (
        action.command == "analyze-program"
        and not unknown_ownership
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
                log_parts.append(_ownership_note(checkin))
    log_parts.append(_ownership_note(hit))
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
    on_unresolved: Callable[[subprocess.Popen[str], str], None] | None = None,
    on_started: Callable[[dict], None] | None = None,
    on_clearance: Callable[[dict], None] | None = None,
    inherited_fds: tuple[int, ...] = (),
    on_not_started: Callable[[], None] | None = None,
    on_peak: Callable[[int], None] | None = None,
    checkpointed: bool = False,
) -> tuple[int, str]:
    """Drain output without blocking cancellation when a child is silent.

    ``on_peak`` receives the job's measured process-tree peak resident memory
    (every process in its session, sampled about once a second) when it ends.

    ``checkpointed`` makes the deadline follow the unit's declared lifecycle (FP-12):
    each distinct completed checkpoint (a JSON ``*-progress`` event whose integer
    ``completed`` exceeds every earlier one) restarts the idle window, up to
    ``AGENT_DECOMPILE_JOB_MAX_SECONDS`` (default 24 h). A live PID or plain output never
    extends it.
    """
    if not argv:
        return 2, "empty command"
    from agentdecompile_recovery.native_verify_contract import _BOOTSTRAP, clean_environment
    from agentdecompile_recovery.corpus.cross_place import _BOOTSTRAP as _CROSS_BOOTSTRAP
    native_guarded = (len(argv) == 7 and argv[1:4] == ["-I", "-S", "-c"]
                      and argv[4] in {_BOOTSTRAP, _CROSS_BOOTSTRAP})
    if inherited_fds:
        from agentdecompile_recovery.corpus import cross_place, cross_place_admission
        envelope = json.loads(argv[-1])
        if (not native_guarded or argv[4] != _CROSS_BOOTSTRAP
                or not cross_place.command_matches(argv, envelope.get('params'))
                or inherited_fds != cross_place_admission.lease_fds()
                or envelope.get('generation', {}).get('lease', {}).get('fd') not in inherited_fds):
            raise ValueError('unqualified_inherited_descriptor_dispatch')
    if cancel.is_set():
        if on_not_started: on_not_started()
        return 1, '[cancelled before spawn]'
    proc = subprocess.Popen(argv, cwd=str(cwd), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1, env=clean_environment() if native_guarded else isolated_job_env(argv),
        start_new_session=os.name != "nt", pass_fds=inherited_fds)
    from agentdecompile_recovery.corpus.supervision import process_identity, session_clearance
    reader_stop = None
    reader_thread = None
    admitted_process = {'pid': proc.pid, 'identity_unavailable': True}
    clearance_callback_attempted = False
    try:
        admitted_process = process_identity(proc.pid)
        if on_started:
            on_started(admitted_process)
        lines: queue.Queue[str | None] = queue.Queue(maxsize=128)
        reader_stop = threading.Event()
        def read() -> None:
            assert proc.stdout is not None
            try:
                descriptor = proc.stdout.fileno()
                os.set_blocking(descriptor, False)
                while not reader_stop.is_set():
                    try:
                        raw = os.read(descriptor, 4096)
                    except BlockingIOError:
                        reader_stop.wait(.05)
                        continue
                    if not raw: break
                    while not reader_stop.is_set():
                        try: lines.put(raw.decode('utf-8', errors='replace'), timeout=.1); break
                        except queue.Full: pass
            except (OSError, ValueError):
                pass  # Main lifecycle may close the descriptor after bounded drain.
            finally:
                try: lines.put(None, timeout=.1)
                except queue.Full: pass
        reader_thread = threading.Thread(target=read, daemon=True, name=f'agentdecompile-output-{proc.pid}')
        reader_thread.start()
        log = ""
        configured_timeout = timeout_seconds
        if not unlimited and configured_timeout is None:
            try:
                configured_timeout = float(os.environ.get("AGENT_DECOMPILE_JOB_TIMEOUT_SECONDS", "1800"))
            except ValueError:
                configured_timeout = 1800.0
        deadline = None if unlimited else time.monotonic() + max(1.0, float(configured_timeout))
        checkpoints = 0
        best_completed = None
        pending_text = ""
        hard_deadline = None
        if checkpointed and deadline is not None:
            try:
                max_seconds = float(os.environ.get("AGENT_DECOMPILE_JOB_MAX_SECONDS", "86400"))
            except ValueError:
                max_seconds = 86400.0
            hard_deadline = time.monotonic() + max(float(configured_timeout), max_seconds)
        cancellation_at = None
        cancellation_forced = False
        exited_at = None
        timed_out = False
        peak_rss = 0
        next_sample = 0.0
        while True:
            now = time.monotonic()
            if on_peak is not None and os.name != "nt" and now >= next_sample and exited_at is None:
                from agentdecompile_recovery.corpus.dashboard.resource_admission import session_rss_bytes
                peak_rss = max(peak_rss, session_rss_bytes(proc.pid))
                next_sample = now + 1.0
            if deadline is not None and now >= deadline and cancellation_at is None:
                timed_out = True
                cancellation_at = now
                if checkpointed and hard_deadline is not None and now >= hard_deadline:
                    log += (f"\n[timed out: reached the job maximum (AGENT_DECOMPILE_JOB_MAX_SECONDS) "
                            f"after {checkpoints} completed checkpoints]\n")
                elif checkpointed:
                    log += (f"\n[timed out: no new completed checkpoint within {configured_timeout:g} seconds "
                            f"({checkpoints} completed checkpoints)]\n")
                else:
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
                break
            try:
                line = lines.get(timeout=.1)
            except queue.Empty:
                # Process exit can precede the reader thread delivering its final
                # buffered output. Only the pipe EOF sentinel proves it is drained.
                continue
            if line is None:
                # Pipe EOF does not end the child lifetime or its deadline.
                if proc.poll() is not None:
                    break
                continue
            log = (log + line)[-MAX_LOG_BYTES:]
            if checkpointed and deadline is not None:
                pending_text += line
                *complete, pending_text = pending_text.split("\n")
                pending_text = pending_text[-65536:]
                for text in complete:
                    try:
                        event = json.loads(text)
                    except (ValueError, TypeError):
                        continue
                    done = event.get("completed") if isinstance(event, dict) else None
                    if (isinstance(done, int) and not isinstance(done, bool)
                            and str(event.get("event", "")).endswith("-progress")
                            and (best_completed is None or done > best_completed)):
                        best_completed = done
                        checkpoints += 1
                        deadline = min(hard_deadline, time.monotonic() + max(1.0, float(configured_timeout)))
            if on_output: on_output(log)
        returncode = proc.poll()
        if returncode is None:
            try:
                returncode = proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                returncode = None
        if on_peak is not None and peak_rss:
            try:
                on_peak(peak_rss)
            except Exception:  # profiling must never change a job's outcome
                pass
        if returncode is None and on_unresolved is not None:
            on_unresolved(proc, log)
            returncode = proc.poll()
        if returncode is None or session_clearance(admitted_process) != "clear":
            return 124, log + "\n[process did not reach a terminal state; ownership remains unresolved]\n"
        if on_clearance:
            clearance_callback_attempted = True
            on_clearance(admitted_process)
        return (124 if timed_out else int(returncode)), log

    except BaseException as exc:
        # Every post-spawn exception still owns this exact session. A leader
        # exiting after TERM does not prove its descendants have stopped.
        def stop_owned(sig):
            try:
                if os.name != 'nt': os.killpg(proc.pid, sig)
                elif proc.poll() is None:
                    proc.kill() if sig == signal.SIGKILL else proc.terminate()
            except ProcessLookupError:
                pass
        stop_owned(signal.SIGTERM)
        try: proc.wait(timeout=2)
        except subprocess.TimeoutExpired: pass
        clear = proc.poll() is not None and session_clearance(admitted_process) == 'clear'
        if not clear:
            stop_owned(signal.SIGKILL)
            try: proc.wait(timeout=2)
            except subprocess.TimeoutExpired: pass
            clear = proc.poll() is not None and session_clearance(admitted_process) == 'clear'
        recorded = False
        if clear and on_clearance and not clearance_callback_attempted:
            try:
                clearance_callback_attempted = True
                on_clearance(admitted_process)
                recorded = True
            except Exception:
                pass  # The durable failure still retains its resource claim.
        suffix = 'owned session cleared after failure' if clear and recorded else 'ownership remains unresolved'
        return 124, '[executor callback/setup failure: ' + str(exc) + '; ' + suffix + ']'
    finally:
        if reader_stop is not None: reader_stop.set()
        # Nonblocking reads and stop-aware queue waits bound shutdown even if
        # a surviving descendant keeps the write end open indefinitely.
        if reader_thread is not None: reader_thread.join(timeout=.5)
        if proc.stdout is not None: proc.stdout.close()


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


def _record_peak(action_id: str) -> Callable[[int], None]:
    def record(peak_bytes: int) -> None:
        from agentdecompile_recovery.corpus.dashboard.resource_admission import default_profile_store
        default_profile_store().record(action_id, peak_bytes)
    return record


def _admission_refusal(action_id: str) -> dict[str, Any] | None:
    """Resource admission for one dispatch; None admits. Disabled by AGENTDECOMPILE_RESOURCE_ADMISSION=off."""
    from agentdecompile_recovery.corpus.dashboard import resource_admission as ra
    if not ra.gate_enabled():
        return None
    # Capacity that may free up is waited for in the job queue (runtime_admit); refuse here
    # only what waiting cannot fix: a blocked class or a need larger than this worker.
    never = ra.never_feasible(action_id)
    if never is not None:
        return {"ok": False, "actionId": action_id, "error": never, "nextAction": "capacity_prerequisite",
                "wakeCondition": "capable_worker_available", "admission": {"outcome": "refuse"}}
    running = [job.action_id for job in STORE.list(compact=True) if job.status in {"queued", "running"}]
    decision = ra.dispatch_gate(action_id, running)
    if decision.outcome in {"admit", "refuse", "profile_first"}:
        return None
    return {"ok": False, "actionId": action_id, "error": decision.reason, "nextAction": "wait",
            "wakeCondition": "capacity_available" if decision.outcome == "refuse" else "enforcement_available",
            "admission": {"outcome": decision.outcome, "needBytes": decision.need_bytes,
                          "availableBytes": decision.available_bytes, "basis": decision.basis}}


def _active_duplicate(action_id: str, params: dict[str, Any]) -> JobRecord | None:
    """Return an existing active job targeting the same work directory.

    Recovery outputs are append-only ledgers; admitting two writers corrupts
    reuse accounting and doubles compiler work.
    """
    direct_image = action_id == "corpus.verify-direct-full-image"
    target = str((params.get("work-dir") if direct_image else
                  params.get("workDir") or params.get("work_dir")) or "").strip()
    if not target:
        return None
    if direct_image:
        target_key = _canonical_resource_path(target, base=(live_root() or Path.cwd()).resolve())
        if target_key is None:
            return None
    else:
        try:
            target_key = str(Path(target).expanduser().resolve())
        except (OSError, RuntimeError, ValueError):
            target_key = target
    for existing in STORE.list(compact=True):
        if existing.action_id != action_id or existing.status not in {"queued", "running", "cancelling"}:
            continue
        if direct_image:
            other = _canonical_resource_path(
                existing.params.get("work-dir"),
                base=Path(existing.execution_root) if existing.execution_root else
                (live_root() or Path.cwd()).resolve(),
            )
        else:
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
    direct_image = action_id == "corpus.verify-direct-full-image"
    work_dir = str((params.get("work-dir") if direct_image else
                    params.get("workDir") or params.get("work_dir") or params.get("out-dir")) or "").strip()
    if not db or not work_dir:
        return None
    if direct_image:
        root = (live_root() or Path.cwd()).resolve()
        db = _canonical_resource_path(db, base=root)
        work_dir = _canonical_resource_path(work_dir, base=root)
        if db is None or work_dir is None:
            return None
    else:
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
    _mcp_reserve: Callable[[str], Any] | None = None,
    _execution_context: Any = None,
) -> tuple[dict[str, Any], int]:
    action = action_by_id(action_id)
    if action is None:
        return {"error": f"unknown action {action_id}"}, 404
    if _execution_context is None:
        filled = apply_defaults(action, dict(params or {}), context)
    else:
        # The private coordinator context is consumed here, never serialized or
        # retained as the child's root preparation lifecycle capability.
        captured_db = _execution_context.db
        def require_captured_db(values):
            raw = (values or {}).get('db')
            if raw not in (None, ''):
                selected = Path(str(raw)).expanduser()
                if not selected.is_absolute():
                    selected = _execution_context.root / selected
                if selected.resolve() != captured_db:
                    raise ValueError('Preparation child database conflicts with its captured workspace.')
        require_captured_db(params)
        require_captured_db(context)
        filled = apply_defaults(action, dict(params or {}), context,
                                defaults=_execution_context.execution_defaults, db=captured_db)
        require_captured_db(filled)
        if filled.get('db') not in (None, ''):
            filled['db'] = str(captured_db)
    if action.backend == 'match-review':
        from .match_review import freeze
        from ...match_review import ReviewError
        from ..common import review_error_status
        try:
            filled = freeze(filled, decide=action.command == 'decide')
        except ReviewError as exc:
            return exc.result(), review_error_status(exc)
    duplicate = _active_duplicate(action.id, filled)
    if duplicate is not None and not dry_run:
        return {"ok": True, "deduplicated": True, "job": duplicate.to_dict()}, 202
    errors = validate_params(action, filled, confirm=confirm)
    if errors:
        return {"error": "; ".join(errors), "actionId": action.id}, 400
    owner = None if _read_only_supervisor_status(action.id, filled) else _external_pipeline_owner(action.id, filled)
    if owner is not None and not dry_run:
        return {
            "ok": False,
            "actionId": action.id,
            "error": "External pipeline already owns this database and workspace; inspect or adopt it before starting another writer.",
            "externalOwner": owner,
        }, 409
    if action.identity_scope:
        key = identity_lock_key(filled)
        if not key:
            return {"error": "identity writer needs --db", "actionId": action.id}, 400
        filled["db"] = key
    if action.backend == "preparation" and not dry_run:
        from agentdecompile_recovery.corpus.dashboard import preparation
        try:
            run = preparation.submit(filled, resume=bool(filled.get("resume", False)))
        except preparation._PreparationIssuanceWait as exc:
            return preparation.authority_refusal(exc)
        except preparation._PreparationControlWait as exc:
            return preparation.authority_refusal(exc)
        except preparation._PreparationAuthorityRefused as exc:
            return preparation.authority_refusal(exc)
        except (ValueError, OSError) as exc:
            return {"error": str(exc)}, 400
        job = get_job(run.get("jobId", ""))
        return {"ok": run["status"] != "blocked", "run": run, "job": job.to_dict() if job else {"id": run.get("jobId", ""), "status": run["status"]}}, 202
    argv = build_command(action, filled)
    if dry_run:
        return {"ok": True, "dryRun": True, "action": action.to_dict(), "argv": argv, "params": filled}, 200
    if action.mutating or action.identity_scope or action.long_running:
        health = STORE.event_store_health()
        if not health['ok']:
            return {"ok": False, "actionId": action.id, "nextAction": "wait",
                    "wakeCondition": "event_store_available",
                    "error": f"Job event store unavailable; unsafe dispatch refused: {health['reason']}"}, 503
    refusal = _admission_refusal(action.id)
    if refusal is not None:
        return refusal, 503
    job = STORE.start(
        action,
        filled,
        argv,
        mcp_reserve=_mcp_reserve,
        trusted_preparation_facts_inventory=(
            _trusted_context is _PREPARATION_FACTS_INVENTORY
            and action.id == "mcp.execute-script"
        ),
        trusted_preparation_probe=(
            _trusted_context is _PREPARATION_PROBE
            and action.id == "mcp.execute-script"
        ),
        _execution_root=_execution_context.root if _execution_context is not None else None,
    )
    return {"ok": True, "job": job.to_dict()}, 202


def _start_preparation_facts_inventory(
    params: dict[str, Any], context: dict[str, Any], *, _mcp_reserve=None, _execution_context=None
) -> tuple[dict[str, Any], int]:
    """Submit the preparation-owned, read-only inventory script."""
    return start_job(
        "mcp.execute-script",
        params,
        context=context,
        confirm=True,
        _trusted_context=_PREPARATION_FACTS_INVENTORY,
        _mcp_reserve=_mcp_reserve,
        _execution_context=_execution_context,
    )


def _start_preparation_probe(
    params: dict[str, Any], context: dict[str, Any], *, _mcp_reserve=None, _execution_context=None
) -> tuple[dict[str, Any], int]:
    """Submit a preparation-owned, bounded read-only probe."""
    return start_job(
        "mcp.execute-script",
        params,
        context=context,
        confirm=True,
        _trusted_context=_PREPARATION_PROBE,
        _mcp_reserve=_mcp_reserve,
        _execution_context=_execution_context,
    )


def list_jobs(*, compact: bool = False) -> list[JobRecord]:
    return STORE.list(compact=compact)


def get_job(job_id: str, *, compact: bool = False) -> JobRecord | None:
    return STORE.get(job_id, compact=compact)


def cancel_job(job_id: str) -> JobRecord | None:
    return STORE.cancel(job_id)
