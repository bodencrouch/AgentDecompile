"""Durable, missing-only project preparation shared by both frontends."""
from __future__ import annotations

import hashlib
import copy
import errno
from contextlib import contextmanager
import json
import math
import os
import socket
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .common import live_db, live_root, query_db
from . import admission_budget, mcp_budget
from .retry_policy import MAX_ACTION_ATTEMPTS, decide_retry, refusal_outcome
from agentdecompile_recovery.corpus.ghidra_project import ghidra_program_path
from agentdecompile_recovery.corpus.donor_schedule import spanning_forest_pairs
from .workflow import DEFAULT_BUDGET_SECONDS, MAX_BUDGET_SECONDS, STAGES as RECOVERY_STAGES, VERSION, transient_failure

_LOCK = threading.RLock()
_BSIM_LOCK = threading.Lock()
_ACTIVE: dict[str, Any] = {}
_LEASES: dict[str, Any] = {}
_WAITING: set[str] = set()
_ADMISSION_WAKE = threading.Event()
_ADMISSION_THREAD: threading.Thread | None = None
_STAGES = [('inspect', 'Read project'), ('protection', 'Prepare analysis image'),
           ('analysis', 'Analyze missing programs'), ('facts', 'Extract function facts'),
           ('bsim', 'Index similarity signatures'), ('matching', 'Match related builds')] + RECOVERY_STAGES
_ANALYSIS_PROBE = """import json
from ghidra.framework import Application
try:
    from ghidra.program.util import GhidraProgramUtilities
    pending = bool(GhidraProgramUtilities.shouldAskToAnalyze(currentProgram)) or not bool(GhidraProgramUtilities.isAnalyzed(currentProgram))
except Exception:
    pending = None
try:
    analysisState = currentProgram.getAnalysisState()
    stateDone = bool(analysisState.isDone()) if analysisState is not None and hasattr(analysisState, 'isDone') else None
except Exception:
    stateDone = None
needsAnalysis = False if pending is False else (True if stateDone is False else (False if stateDone is True else True if pending is None else pending))
try:
    observedProgramPath = str(globals().get('programPath') or currentProgram.getDomainFile().getPathname())
except Exception:
    observedProgramPath = ''
__result__ = json.dumps({'programPath': observedProgramPath, 'needsAnalysis': needsAnalysis, 'executablePath': str(currentProgram.getExecutablePath()), 'architecture': str(currentProgram.getLanguageID()), 'ghidraVersion': str(Application.getApplicationVersion()), 'workSize': int(currentProgram.getFunctionManager().getFunctionCount())})"""


def _same_program_path(left: Any, right: Any) -> bool:
    """Require the exact Ghidra DomainFile path before accepting a probe."""
    return bool(left and right and str(left).replace('\\', '/').strip().strip('/') == str(right).replace('\\', '/').strip().strip('/'))


def _effective_recovery_family(stored: Any, locator: Any, program: Any, binary_id: Any) -> str:
    """Group only exact project-folder peers unless a catalog family exists.

    ``program_binding`` is durable evidence that a binary belongs to one
    folder-qualified Ghidra project object.  Its full parent folder is a
    conservative variant boundary: sibling builds in ``/K1`` can be compared,
    while ``/TSL`` and nested engine/game folders stay separate.  A stored
    non-placeholder family remains authoritative user metadata.  Root-level
    and unbound programs remain isolated rather than being grouped by filename.
    """
    stored_family = str(stored or '').strip()
    if stored_family and not stored_family.startswith('unclassified:'):
        return stored_family
    normalized_locator = str(locator or '').replace('\\', '/').strip().rstrip('/')
    parts = [part for part in str(program or '').replace('\\', '/').strip().split('/') if part]
    if normalized_locator and len(parts) > 1:
        project_id = hashlib.sha256(normalized_locator.encode()).hexdigest()[:16]
        return f"project-folder:{project_id}:{'/'.join(parts[:-1])}"
    return stored_family or f'unclassified:{binary_id}'


def _discard_unverified_probe(checkpoint: dict[str, Any], requested: str, observed: str = '') -> bool:
    """Remove probe-derived state that cannot be tied to its selected program."""
    if _same_program_path(checkpoint.get('observedProgramPath'), requested):
        return False
    for key in (
        'analysisConfirmed', 'analysisCheckedAt', 'needsAnalysis', 'executablePath',
        'architecture', 'ghidraVersion', 'workSize', 'protection',
        'externalSourceAvailable', 'programFingerprint', 'arch', 'toolchain',
        'targetImage', 'bsimComplete', 'bsimUrl', 'bsimReceipt', 'bsimFingerprint',
        'knowledgeComplete', 'knowledgeCursor', 'knowledgeFingerprint',
        'knowledgeAvailable', 'workflow', 'factsComplete', 'factsPath',
        'binaryId', 'slug', 'repoPath', 'recoveryFamily',
    ):
        checkpoint.pop(key, None)
    checkpoint['probeMismatch'] = {
        'requestedProgramPath': requested,
        'observedProgramPath': observed or str(checkpoint.get('observedProgramPath') or ''),
        'at': time.time(),
    }
    checkpoint.pop('observedProgramPath', None)
    return True


def _accept_probe(checkpoint: dict[str, Any], requested: str, payload: dict[str, Any]) -> bool:
    observed = str(payload.get('programPath') or '')
    if not _same_program_path(requested, observed):
        _discard_unverified_probe(checkpoint, requested, observed)
        return False
    checkpoint.update(
        observedProgramPath=observed,
        executablePath=payload.get('executablePath'), analysisCheckedAt=time.time(),
        needsAnalysis=payload.get('needsAnalysis'),
        **{key: payload.get(key) for key in ('architecture', 'ghidraVersion', 'workSize')},
    )
    checkpoint.pop('probeMismatch', None)
    return True


def _matching_concurrency() -> int:
    # corpus.match-pair is a standalone subprocess that only reads/writes the
    # sqlite corpus DB — it never touches the shared PyGhidra JVM/project, so
    # it isn't bound by Ghidra's single-session limitation the way analysis
    # and bsim are. Bounded (not unbounded) because the host also runs a
    # single shared Ghidra JVM and other preparation runs concurrently, and
    # this box has a history of OOM under combined memory pressure.
    raw = os.environ.get('AGENT_DECOMPILE_MATCH_CONCURRENCY', '')
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 0
    if value > 0:
        return value
    return max(1, min(6, (os.cpu_count() or 4)))


def _budget_expired(deadline: Any) -> bool:
    return deadline is not None and time.time() >= float(deadline)


def _merge_stages(previous: dict[str, Any]) -> list[dict[str, Any]]:
    by_key = {item.get('key'): dict(item) for item in previous.get('stages') or [] if item.get('key')}
    stages = []
    for key, title in _STAGES:
        if key in by_key:
            row = by_key[key]
            row['title'] = title
            stages.append(row)
        else:
            stages.append({'key': key, 'title': title, 'status': 'queued', 'completed': 0, 'total': None, 'reason': ''})
    return stages


def _ensure_stages(row: dict[str, Any]) -> bool:
    before = [item.get('key') for item in row.get('stages') or []]
    row['stages'] = _merge_stages(row)
    after = [item.get('key') for item in row['stages']]
    if after != before:
        row['workflowVersion'] = VERSION
        return True
    return False


def _reset_resume_projection(row: dict[str, Any]) -> bool:
    """Make a renewed coordinator show only work it still has to reach."""
    stages = row.get('stages') or []
    first_pending = next((index for index, stage in enumerate(stages)
                          if stage.get('status') != 'completed'), None)
    if first_pending is None:
        return False
    changed = False
    stale_fields = {
        'jobId', 'jobStatus', 'currentAction', 'currentProgram', 'currentPair',
        'startedAt', 'lastJobUpdateAt', 'heartbeatAt', 'nextFallback', 'retryAt',
        'pauseRequestedAt', 'executionDeadlineAt', 'executionLimitSeconds',
    }
    for stage in stages[first_pending:]:
        if stage.get('status') == 'completed':
            continue
        changed = True
        stage.update(status='queued', reason='Waiting for the renewed workflow to reach this stage.')
        for field in stale_fields:
            stage.pop(field, None)
    if changed:
        row.update(
            status='queued', error='',
            currentStage=stages[first_pending].get('key', ''),
            currentAction='', currentProgram='',
        )
    return changed


def _lock_lease(lease: Any) -> None:
    if os.name == 'nt':
        import msvcrt
        lease.seek(0)
        if not lease.read(1):
            lease.write('0')
            lease.flush()
        lease.seek(0)
        try:
            msvcrt.locking(lease.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if getattr(exc, 'winerror', None) in {33, 36} or exc.errno in {errno.EAGAIN, errno.EDEADLK}:
                raise BlockingIOError(exc.errno, 'Lease is busy') from exc
            raise
    else:
        import fcntl
        fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _directory() -> Path:
    root = live_root()
    if root is None:
        raise ValueError('Choose a server workspace before preparing projects.')
    directory = root / 'preparations'
    return directory


MAX_BIRTH_LOG_BYTES = 4_194_304
MAX_BIRTH_RECORD_BYTES = 512
MAX_ISSUED_OBJECTIVES = 10_000
_SESSION = object()
_SESSION_ID = uuid.uuid4().hex
_AUTHORITIES: dict[str, Any] = {}
_HEALTHY: dict[tuple[str, str], Any] = {}
_BIRTHS: dict[tuple[str, str], Any] = {}
_FAULTS: dict[tuple[str, str], Any] = {}
_NAMESPACE_FAULTS: dict[str, Any] = {}
_NAMESPACE_LIMITS: dict[str, Any] = {}
_DIAGNOSTICS: dict[tuple[str, str], dict[str, Any]] = {}
_SUSPENDED: set[tuple[str, str]] = set()
_NEXT_NAMESPACE_PROBE: dict[str, float] = {}
_COMMAND_FAULTS: dict[tuple[str, str], Any] = {}
_NEXT_CONTROL_PROBE: dict[tuple[str, str], float] = {}


class _PreparationAuthorityRefused(Exception):
    def __init__(self, decision):
        self.decision = decision
        super().__init__(decision['reason'])


class _PreparationIssuanceWait(Exception):
    def __init__(self, run_id):
        self.decision = {'preparationId': run_id, 'phase': 'initialization',
                         'reason': 'Preparation namespace issuance is busy; retry after the namespace lock becomes available.',
                         'nextAction': 'preparation_issuance_busy'}
        super().__init__(self.decision['reason'])


class _PreparationControlWait(Exception):
    def __init__(self, run_id, root):
        with _LOCK:
            current = _AUTHORITIES.get(run_id)
            witness = _HEALTHY.get((str(root), run_id))
            metadata = witness.snapshot.get('authority', {}) if witness else {}
            if current is not None and current.root == root:
                metadata = {'generation': current.generation, 'rowRevision': current.revision}
        self.decision = {'preparationId': run_id, 'phase': 'control',
                         'generation': metadata.get('generation'),
                         'lastCommittedRevision': metadata.get('rowRevision'),
                         'reason': 'Preparation control is busy; retry after the command lock becomes available.',
                         'nextAction': 'preparation_control_busy'}
        super().__init__(self.decision['reason'])


def authority_refusal(exc):
    """The sole wire projection; no arbitrary exception or ledger data escapes."""
    if not isinstance(exc, (_PreparationIssuanceWait, _PreparationControlWait, _PreparationAuthorityRefused)):
        raise TypeError('Not a preparation refusal')
    decision = exc.decision
    reason = str(decision.get('reason', 'Preparation authority is unavailable.'))[:512]
    action = decision.get('nextAction', 'preparation_continuity_required')
    if action not in {'preparation_authority_lost', 'preparation_continuity_required', 'preparation_persistence_failed', 'preparation_issuance_busy', 'preparation_issuance_limit_reached', 'preparation_control_busy'}:
        action = 'preparation_continuity_required'
    phase = decision.get('phase', 'checkpoint')
    if phase not in {'intent', 'handoff', 'acknowledgement', 'checkpoint', 'control', 'initialization'}:
        phase = 'checkpoint'
    revision = decision.get('lastCommittedRevision')
    body = {'ok': False, 'status': 'blocked', 'error': reason, 'reason': reason,
            'nextAction': action, 'wakeCondition': 'explicit_preparation_continuity_reconciliation',
            'preparationId': decision.get('preparationId') if _valid_id(decision.get('preparationId')) else None,
            'generation': decision.get('generation') if _valid_id(decision.get('generation')) else None,
            'lastCommittedRevision': revision if type(revision) is int and revision >= 0 else None,
            'phase': phase, 'durable': False}
    if isinstance(exc, _PreparationIssuanceWait):
        body.update(status='waiting', wakeCondition='birth_namespace_lock_available',
                    retryable=True, retryAfterSeconds=1, noEffect=True)
    elif isinstance(exc, _PreparationControlWait):
        body.update(status='waiting', wakeCondition='control_command_lock_available',
                    retryable=True, retryAfterSeconds=1, noEffect=True)
    elif action == 'preparation_issuance_limit_reached':
        kind = decision['limitKind']
        limits = {'bytes': MAX_BIRTH_LOG_BYTES, 'record_bytes': MAX_BIRTH_RECORD_BYTES, 'issued_ids': MAX_ISSUED_OBJECTIVES}
        body.update(wakeCondition='qualified_birth_log_capacity_revision', retryable=False,
                    noEffect=True, limitKind=kind, limit=limits[kind])
    return body, 503 if action == 'preparation_persistence_failed' else 409


def _refusal(run_id, action='preparation_continuity_required', phase='checkpoint', authority=None, reason=None):
    return _PreparationAuthorityRefused({
        'preparationId': run_id, 'nextAction': action, 'phase': phase,
        'generation': authority.generation if authority else None,
        'lastCommittedRevision': authority.revision if authority else None,
        'reason': reason or 'Preparation requires explicit continuity reconciliation.'})


def _valid_id(value):
    return isinstance(value, str) and len(value) == 32 and all(c in '0123456789abcdef' for c in value)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def _load_row(path):
    row = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
    if not isinstance(row, dict):
        raise ValueError('Preparation row must be an object')
    return row


def _sync_directory(path):
    if os.name == 'posix':
        descriptor = os.open(str(path), os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _atomic_json(path, value, suffix):
    temporary = path.with_name(path.name + '.' + suffix + '.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    _sync_directory(path.parent)


class _NewObjectiveWitness:
    def __init__(self, root, run_id, namespace):
        self.root, self.run_id, self.namespace = root, run_id, namespace
        self.session, self.used = _SESSION, False


class _HealthyContinuityWitness:
    def __init__(self, authority, snapshot):
        self.root, self.session = authority.root, _SESSION
        self.snapshot = copy.deepcopy(snapshot)
        self.valid = True


class _ExecutionSlot:
    def __init__(self, authority):
        self.authority = authority
        self.intent = uuid.uuid4().hex
        self.job_id = None
        self.worker_start_attempted = False
        self.entered = False
        self.finished = False


class _PreparationAuthority:
    def __init__(self, root, db, run_id, lease, row, *, birth=None, committed=None):
        from .actions.catalog import env_defaults
        self.root, self.directory, self.db = root, root / 'preparations', db
        self.execution_defaults = env_defaults(root=root, db=db)
        self.run_id, self.lease, self.row = run_id, lease, row
        self.session, self.generation = _SESSION, uuid.uuid4().hex
        self.revision = (committed or {}).get('authority', {}).get('rowRevision', 0)
        self.committed = copy.deepcopy(committed)
        self.uncertain = None
        self.birth = birth
        self.gate = threading.RLock()
        self.state = 'current'
        self.failure_decision = None
        self.slot = None
        self.owner = (socket.gethostname(), os.getpid(), _process_start(os.getpid()))

    def root_start(self, event, job_id):
        # Called only outside the job-store lock. The submit gate is reentrant.
        with self.gate:
            if self.slot is None or (self.slot.job_id is not None and self.slot.job_id != job_id):
                raise _refusal(self.run_id, authority=self, phase='handoff')
            self.slot.job_id = job_id
            if event == 'attempted':
                _check(self, dispatch=True, phase='handoff')
                self.slot.worker_start_attempted = True
            elif event == 'entered':
                self.slot.entered = True
            elif event == 'finished':
                self.slot.finished = True
                _retire_capacity(self.slot)
                _release_lease(self.run_id, expectedAuthority=self)


def _poison(authority, exc):
    key = (str(authority.root), authority.run_id)
    with _LOCK:
        if _AUTHORITIES.get(authority.run_id) is not authority:
            return  # An old callback cannot invalidate a successor's witness.
        if authority.failure_decision is None:
            authority.failure_decision = copy.deepcopy(authority_refusal(exc)[0])
        authority.state = 'continuity_required'
        witness = _HEALTHY.get(key)
        if witness is not None:
            witness.valid = False
        _FAULTS[key] = authority
        _SUSPENDED.add(key)
    _diagnostic(authority.root, authority.run_id, _PreparationAuthorityRefused(authority.failure_decision))


def _diagnostic(root, run_id, exc):
    body, _ = authority_refusal(exc)
    key = (str(root), run_id)
    with _LOCK:
        _DIAGNOSTICS[key] = body
        while len(_DIAGNOSTICS) > 100:
            _DIAGNOSTICS.pop(next(iter(_DIAGNOSTICS)))
        if isinstance(exc, _PreparationIssuanceWait):
            _NEXT_NAMESPACE_PROBE[str(root)] = time.monotonic() + 1
            while len(_NEXT_NAMESPACE_PROBE) > 100:
                _NEXT_NAMESPACE_PROBE.pop(next(iter(_NEXT_NAMESPACE_PROBE)))
        elif isinstance(exc, _PreparationControlWait):
            _NEXT_CONTROL_PROBE[key] = time.monotonic() + 1
            while len(_NEXT_CONTROL_PROBE) > 100:
                _NEXT_CONTROL_PROBE.pop(next(iter(_NEXT_CONTROL_PROBE)))
            if key in _HEALTHY and key not in _SUSPENDED and key not in _FAULTS:
                _WAITING.add(run_id)
        elif body['nextAction'] == 'preparation_issuance_limit_reached':
            _NAMESPACE_LIMITS[str(root)] = exc
        elif not exc.decision.get('leaseBusy'):
            _SUSPENDED.add(key)
            _WAITING.discard(run_id)
    return body


def _limit(run_id, kind):
    return _PreparationAuthorityRefused({'preparationId': run_id, 'phase': 'initialization',
        'nextAction': 'preparation_issuance_limit_reached', 'limitKind': kind,
        'reason': 'Preparation birth-log capacity requires a qualified revision.'})


def _birth_record(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def _scan_birth_log(path, run_id):
    if path.stat().st_size > MAX_BIRTH_LOG_BYTES:
        raise _limit(run_id, 'bytes')
    issued, total, namespace = set(), 0, None
    with path.open('rb') as stream:
        while True:
            line = stream.readline(MAX_BIRTH_RECORD_BYTES + 1)
            if not line:
                break
            total += len(line)
            if len(line) > MAX_BIRTH_RECORD_BYTES:
                raise _limit(run_id, 'record_bytes')
            if total > MAX_BIRTH_LOG_BYTES:
                raise _limit(run_id, 'bytes')
            if not line.endswith(b'\n'):
                raise ValueError('Partial birth record')
            record = json.loads(line.decode('utf-8'), object_pairs_hook=_unique_object)
            if not isinstance(record, dict) or _birth_record(record) != line:
                raise ValueError('Noncanonical birth record')
            if namespace is None:
                if set(record) != {'schema', 'kind', 'namespaceId'} or type(record['schema']) is not int or record['schema'] != 1 or record['kind'] != 'namespace' or not _valid_id(record['namespaceId']):
                    raise ValueError('Invalid namespace record')
                namespace = record['namespaceId']
            else:
                if set(record) != {'kind', 'runId', 'birthSessionId'} or record['kind'] != 'objective-issued' or not _valid_id(record['runId']) or not _valid_id(record['birthSessionId']) or record['runId'] in issued:
                    raise ValueError('Invalid issuance record')
                issued.add(record['runId'])
                if len(issued) > MAX_ISSUED_OBJECTIVES:
                    raise _limit(run_id, 'issued_ids')
    if namespace is None:
        raise ValueError('Missing namespace record')
    return namespace, issued, total


def _issue_new_objective(root, run_id):
    """One acquisition attempt; no global/gate/job lock may enclose this call."""
    if not _valid_id(run_id):
        raise ValueError('Invalid preparation ID')
    root_key, key = str(root), (str(root), run_id)
    if root_key in _NAMESPACE_FAULTS:
        raise _NAMESPACE_FAULTS[root_key]
    if root_key in _NAMESPACE_LIMITS:
        raise _NAMESPACE_LIMITS[root_key]
    lock = None
    try:
        lock = (root / '.preparation-authority-births-v1.lock').open('a+')
        try:
            _lock_lease(lock)
        except BlockingIOError as exc:
            raise _PreparationIssuanceWait(run_id) from exc
        # A concurrent issuer may have faulted after our optimistic precheck.
        if root_key in _NAMESPACE_FAULTS:
            raise _NAMESPACE_FAULTS[root_key]
        if root_key in _NAMESPACE_LIMITS:
            raise _NAMESPACE_LIMITS[root_key]
        path = root / '.preparation-authority-births-v1.jsonl'
        directory = root / 'preparations'
        if not path.exists():
            if directory.exists():
                raise _refusal(run_id, phase='initialization', reason='Legacy preparation namespace requires continuity reconciliation.')
            with path.open('xb') as stream:
                header = _birth_record({'schema': 1, 'kind': 'namespace', 'namespaceId': uuid.uuid4().hex})
                if stream.write(header) != len(header):
                    raise OSError('Incomplete namespace write')
                stream.flush()
                os.fsync(stream.fileno())
            _sync_directory(root)
            directory.mkdir()
            _sync_directory(root)
        if not directory.is_dir():
            raise _refusal(run_id, phase='initialization', reason='Established preparation directory is unavailable; reconcile continuity before issuance.')
        namespace, issued, total = _scan_birth_log(path, run_id)
        if run_id in issued or (directory / (run_id + '.json')).exists():
            witness = _BIRTHS.get(key)
            if witness and witness.session is _SESSION and not witness.used and witness.namespace == namespace:
                return witness
            raise _refusal(run_id, phase='initialization', reason='Established objective has no usable same-session creation witness.')
        record = _birth_record({'kind': 'objective-issued', 'runId': run_id, 'birthSessionId': _SESSION_ID})
        if len(issued) >= MAX_ISSUED_OBJECTIVES:
            raise _limit(run_id, 'issued_ids')
        if len(record) > MAX_BIRTH_RECORD_BYTES:
            raise _limit(run_id, 'record_bytes')
        if total + len(record) > MAX_BIRTH_LOG_BYTES:
            raise _limit(run_id, 'bytes')
        with path.open('ab') as stream:
            if stream.write(record) != len(record):
                raise OSError('Incomplete issuance append')
            stream.flush()
            os.fsync(stream.fileno())
        _sync_directory(root)
        witness = _NewObjectiveWitness(root, run_id, namespace)
        _BIRTHS[key] = witness
        return witness
    except _PreparationIssuanceWait:
        raise
    except _PreparationAuthorityRefused as exc:
        if exc.decision['nextAction'] == 'preparation_issuance_limit_reached':
            _NAMESPACE_LIMITS[root_key] = exc
        raise
    except (OSError, ValueError, UnicodeError) as exc:
        refusal = _refusal(run_id, 'preparation_persistence_failed' if isinstance(exc, OSError) else 'preparation_continuity_required', 'initialization')
        _NAMESPACE_FAULTS[root_key] = refusal
        raise refusal from exc
    finally:
        if lock is not None:
            lock.close()


def _validate_accounting(row):
    if 'objectiveBudget' not in row or 'providerBudget' not in row:
        raise ValueError('Missing established accounting')
    admission_budget.validate(row['objectiveBudget'], row['id'])
    mcp_budget.initialize(row)  # Validation only; the required key exists.
    metadata = row.get('authority')
    if not isinstance(metadata, dict) or set(metadata) != {'schema', 'generation', 'rowRevision'} or type(metadata['schema']) is not int or metadata['schema'] != 1 or not _valid_id(metadata['generation']) or type(metadata['rowRevision']) is not int or metadata['rowRevision'] < 1:
        raise ValueError('Unsupported authority metadata')


def _check(authority, *, dispatch=False, phase='checkpoint'):
    if not isinstance(authority, _PreparationAuthority):
        raise _refusal(None, 'preparation_authority_lost', phase)
    if authority.owner != (socket.gethostname(), os.getpid(), _process_start(os.getpid())):
        refusal = _refusal(authority.run_id, 'preparation_authority_lost', phase, authority)
        _poison(authority, refusal)
        raise refusal
    with _LOCK:
        current = (_AUTHORITIES.get(authority.run_id) is authority and _LEASES.get(authority.run_id) is authority.lease)
        slot_current = authority.slot is not None and authority.slot.authority is authority and _ACTIVE.get(authority.run_id) is authority.slot
    if current and authority.session is _SESSION and authority.state == 'continuity_required' and authority.failure_decision is not None:
        raise _PreparationAuthorityRefused(copy.deepcopy(authority.failure_decision))
    if authority.session is not _SESSION or authority.state != 'current' or not current or authority.lease.closed or (dispatch and not slot_current):
        refusal = _refusal(authority.run_id, 'preparation_authority_lost', phase, authority)
        _poison(authority, refusal)
        raise refusal
    try:
        if authority.row.get('id') != authority.run_id:
            raise ValueError('Canonical identity changed')
        path = authority.directory / (authority.run_id + '.json')
        if authority.committed is None:
            witness = authority.birth
            if witness is None or witness.session is not _SESSION or witness.used or witness.root != authority.root or witness.run_id != authority.run_id or path.exists():
                raise ValueError('Creation witness unavailable')
        else:
            observed = _load_row(path)
            _validate_accounting(observed)
            if observed != authority.committed:
                raise ValueError('Committed snapshot changed')
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
        refusal = _refusal(authority.run_id, 'preparation_persistence_failed' if isinstance(exc, OSError) and not isinstance(exc, FileNotFoundError) else 'preparation_continuity_required', phase, authority)
        _poison(authority, refusal)
        raise refusal from exc


@contextmanager
def _guard(authority, *, dispatch=False, phase='checkpoint'):
    if not isinstance(authority, _PreparationAuthority):
        raise _refusal(None, 'preparation_authority_lost', phase)
    with authority.gate:
        _check(authority, dispatch=dispatch, phase=phase)
        yield


def _write(row, *, authority, phase='checkpoint'):
    with _guard(authority, phase=phase):
        if row is not authority.row:
            refusal = _refusal(authority.run_id, 'preparation_continuity_required', phase, authority, 'Detached snapshots cannot replace the canonical row.')
            _poison(authority, refusal)
            raise refusal
        candidate = copy.deepcopy(row)
        candidate['updatedAt'] = time.time()
        candidate['authority'] = {'schema': 1, 'generation': authority.generation, 'rowRevision': authority.revision + 1}
        try:
            _validate_accounting(candidate)
        except (ValueError, KeyError, TypeError) as exc:
            refusal = _refusal(authority.run_id, 'preparation_continuity_required', phase, authority)
            _poison(authority, refusal)
            raise refusal from exc
        authority.uncertain = candidate
        try:
            _atomic_json(authority.directory / (authority.run_id + '.json'), candidate, authority.generation)
        except Exception as exc:
            refusal = _refusal(authority.run_id, 'preparation_persistence_failed', phase, authority)
            _poison(authority, refusal)
            raise refusal from exc
        row.update(updatedAt=candidate['updatedAt'], authority=candidate['authority'])
        authority.committed, authority.revision = candidate, candidate['authority']['rowRevision']
        authority.uncertain = None
        if authority.birth is not None:
            authority.birth.used = True
        _HEALTHY[(str(authority.root), authority.run_id)] = _HealthyContinuityWitness(authority, candidate)


def _acquire_authority(root, db, run_id, *, birth=None):
    if not _valid_id(run_id):
        raise ValueError('Invalid preparation ID')
    key = (str(root), run_id)
    if key in _FAULTS or key in _SUSPENDED:
        raise _refusal(run_id)
    witness = _HEALTHY.get(key)
    if birth is None and (witness is None or not witness.valid or witness.session is not _SESSION or witness.root != root):
        raise _refusal(run_id, phase='initialization')
    lease = None
    try:
        lease = (root / 'preparations' / (run_id + '.lock')).open('a+')
        _lock_lease(lease)
        committed = None if birth else _load_row(root / 'preparations' / (run_id + '.json'))
        if committed is not None:
            _validate_accounting(committed)
            if committed != witness.snapshot:
                raise ValueError('Healthy snapshot changed')
        authority = _PreparationAuthority(root, db, run_id, lease, copy.deepcopy(committed) if committed else {'id': run_id}, birth=birth, committed=committed)
        with _LOCK:
            if run_id in _AUTHORITIES or run_id in _LEASES:
                raise ValueError('Preparation already has a current owner')
            _AUTHORITIES[run_id], _LEASES[run_id] = authority, lease
        with _guard(authority):
            pass
        return authority
    except _PreparationAuthorityRefused:
        if lease is not None and _LEASES.get(run_id) is not lease:
            lease.close()
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
        if lease is not None:
            lease.close()
        if not isinstance(exc, BlockingIOError):
            if witness is not None:
                witness.valid = False
            _SUSPENDED.add(key)
        refusal = _refusal(run_id, 'preparation_persistence_failed' if isinstance(exc, OSError) and not isinstance(exc, (BlockingIOError, FileNotFoundError)) else 'preparation_continuity_required', 'initialization')
        if isinstance(exc, BlockingIOError):
            refusal.decision['leaseBusy'] = True
            refusal.decision['reason'] = 'Preparation lease is busy; observe the current owner before retrying.'
        raise refusal from exc


def _retire_capacity(expectedSlot):
    if expectedSlot is None:
        return
    with _LOCK:
        run_id = expectedSlot.authority.run_id
        if _ACTIVE.get(run_id) is expectedSlot:
            del _ACTIVE[run_id]
    _ADMISSION_WAKE.set()


def _release_lease(run_id, *, expectedAuthority):
    with expectedAuthority.gate:
        with _LOCK:
            if _AUTHORITIES.get(run_id) is not expectedAuthority or _LEASES.get(run_id) is not expectedAuthority.lease:
                return
            if expectedAuthority.state == 'continuity_required':
                return  # Retained physical fault lease, independent of execution capacity.
            expectedAuthority.state = 'revoked'
            del _AUTHORITIES[run_id]
            del _LEASES[run_id]
        expectedAuthority.lease.close()


def _handoff(authority, dispatch_id, start):
    with _guard(authority, dispatch=True, phase='handoff'):
        command = _read_control(authority.run_id, root=authority.root, strict=True)
        if command.get('operation') == 'pause':
            raise _PauseRequested()
        if command.get('operation') == 'stop' or _budget_expired(command.get('deadline', authority.row.get('deadline'))):
            raise InterruptedError('Preparation control prevents another admission.')
        reservation = authority.row['objectiveBudget']['reservations'].get(dispatch_id)
        if reservation is None or reservation.get('status') != 'intent':
            raise _refusal(authority.run_id, phase='handoff', authority=authority)
        try:
            return start()
        except (_PreparationAuthorityRefused, _PreparationIssuanceWait):
            raise
        except Exception as exc:
            refusal = _refusal(authority.run_id, 'preparation_continuity_required', 'handoff', authority, 'Child start outcome is uncertain; reconcile its committed intent.')
            _poison(authority, refusal)
            raise refusal from exc


def _cancel_child(authority, dispatch_id, job_id, cancel):
    with _guard(authority, dispatch=True, phase='handoff'):
        if authority.row['objectiveBudget']['reservations'].get(dispatch_id, {}).get('jobId') != job_id:
            raise _refusal(authority.run_id, phase='handoff', authority=authority)
        return cancel(job_id)


def _mcp_reservation_capability(authority, *, dispatch_id=None, action_id=None):
    def reserve(tool):
        try:
            with _guard(authority, dispatch=True, phase='intent'):
                attempt = mcp_budget.reserve(authority.row, tool, dispatch_id=dispatch_id, action_id=action_id)
                _write(authority.row, authority=authority, phase='intent')
                return attempt
        except _PreparationAuthorityRefused as exc:
            cause, _ = authority_refusal(exc)
            raise mcp_budget.DispatchRefused({
                'nextAction': 'provider_budget_persistence_failed' if cause['nextAction'] == 'preparation_persistence_failed' else 'provider_authority_lost',
                'reason': cause['reason'], 'wakeCondition': 'explicit_owner_reconciliation',
                'preparationCause': cause}) from exc
    return reserve


def _read(run_id: str) -> dict[str, Any]:
    if not _valid_id(run_id):
        raise ValueError('Invalid preparation ID')
    row = _load_row(_directory() / (run_id + '.json'))
    if row.get('id') != run_id:
        raise ValueError('Preparation row identity mismatch')
    for field in ('createdAt', 'updatedAt', 'deadline'):
        value = row.get(field)
        if field not in row or (field == 'deadline' and value is None):
            continue
        try:
            valid = type(value) in {int, float} and math.isfinite(value)
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError('Invalid preparation time field')
    if 'queuePriority' in row and (type(row['queuePriority']) is not int or not 0 <= row['queuePriority'] <= 100):
        raise ValueError('Invalid preparation priority')
    if 'status' in row and not isinstance(row['status'], str):
        raise ValueError('Invalid preparation status')
    return row


def _process_start(pid: int) -> str | None:
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def _owner_alive(row: dict[str, Any]) -> bool:
    if row.get('ownerHost') and row['ownerHost'] != socket.gethostname():
        return True
    pid = row.get('ownerPid')
    if not isinstance(pid, int) or pid <= 0:
        # Legacy receipts cannot establish that another server has stopped.
        return True
    try:
        os.kill(pid, 0)
        recorded_start = row.get('ownerStart')
        current_start = _process_start(pid)
        if recorded_start and current_start and recorded_start != current_start:
            return False
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False


_WORK_PROGRESS_FIELDS = ('completed', 'total', 'unit', 'currentTarget')


def _bounded_work_progress(value: Any) -> dict[str, Any] | None:
    """Keep the measured counter the UI reads, not the whole producer event.

    A stage counter can come from the durable receipt writer, which emits
    ``{completed, total, unit}``, or from a parsed ``match-pair-progress`` log
    event, which is returned whole and carries further producer fields.  The
    live feed only needs the measured facets ``stageDisplayProgress`` reads.
    """
    if not isinstance(value, dict):
        return None
    bounded = {key: value[key] for key in _WORK_PROGRESS_FIELDS if key in value}
    return bounded or None


def _public_run(row: dict[str, Any], *, detailed: bool = True, live_jobs: list[Any] | None = None) -> dict[str, Any]:
    """Return the live UI contract without replaying every historical action.

    The durable run receipt retains full action logs for audit and recovery.
    Shipping that ever-growing history on every two-second UI poll made the
    workbench appear frozen while a real Ghidra run was active.
    """
    fields = {
        'id', 'locator', 'program', 'slug', 'status', 'scope', 'createdAt',
        'updatedAt', 'workflowVersion', 'queuePriority', 'priorityReason',
        'queuePosition', 'budgetSeconds', 'budgetOrigin', 'deadline', 'error',
        'jobId', 'admissionPending', 'executionLocator',
        'executionProgramPaths', 'stages', 'currentStage', 'retryDecisions', 'objectiveBudget',
    }
    result = {key: row[key] for key in fields if key in row}
    if isinstance(result.get('objectiveBudget'), dict):
        result['objectiveBudget'] = {key: value for key, value in result['objectiveBudget'].items()
                                     if key in {'schema', 'objectiveId', 'maxActionAdmissions', 'consumed',
                                                'allocationRevision', 'priorUsageUnknown', 'accountingScope'}}
    if 'providerBudget' in row:
        result['providerBudget'] = mcp_budget.public(row)
    result['stages'] = []
    for stage in row.get('stages') or []:
        if not isinstance(stage, dict):
            continue
        projected = {
            key: value for key, value in stage.items()
            if key != 'outcomes'
        }
        # A stored retry note describes a waiting/backoff state.  It is not
        # current once a child job is accepted and running; older receipts may
        # still contain it, so normalize the public projection as well.
        if projected.get('status') == 'running':
            projected.pop('nextFallback', None)
            projected.pop('retryAt', None)
            # Dropping every stored counter made a refreshed workbench lose
            # measured progress for the live stage and fall back to a spinner.
            # Keep only the measured facets: the stored value may be a whole
            # parsed producer event rather than the receipt writer's compact
            # counter.  The live child overlay below still takes precedence.
            bounded = _bounded_work_progress(projected.get('workProgress'))
            if bounded:
                projected['workProgress'] = bounded
            else:
                projected.pop('workProgress', None)
        else:
            # A finished or waiting stage's leftover counter is not current work.
            projected.pop('workProgress', None)
        result['stages'].append(projected)
    # Checkpoints can contain complete tool responses.  The activity/stage
    # contract already carries its visible state, so expose concise evidence
    # facets rather than a second copy of every Ghidra response.
    if detailed:
        result['checkpoints'] = {
            program: {key: value for key, value in checkpoint.items()
                      if key in {'analysisConfirmed', 'needsAnalysis', 'factsComplete',
                                 'bsimComplete', 'architecture', 'workSize',
                                 'protection', 'externalSourceAvailable', 'targetImage'}}
            for program, checkpoint in (row.get('checkpoints') or {}).items()
            if isinstance(checkpoint, dict)
        }
        result['events'] = list(row.get('events') or [])[-100:]
    else:
        # Older runs are still represented in the project picker, but their
        # full evidence trail belongs to durable history.  Do not replay every
        # old checkpoint on the live two-second feed.
        result['events'] = list(row.get('events') or [])[-3:]
    # The durable receipt is intentionally cheap to read while PyGhidra is
    # busy.  Its stage job id can lag the scheduler by one admitted child,
    # though, which made the UI name a queued comparison as the live one.
    # Overlay only the current child job; the receipt remains the audit record.
    run_token = f"prepare-{row['id']}"
    active_jobs = [job for job in live_jobs or []
                   if getattr(job, 'status', None) in {'queued', 'running', 'cancelling'}
                   and (getattr(job, 'params', {}) or {}).get('run') == run_token]
    if active_jobs:
        active_jobs.sort(key=lambda job: (
            0 if getattr(job, 'status', None) == 'running' else 1,
            -(float(getattr(job, 'started_at', None) or getattr(job, 'created_at', 0) or 0)),
        ))
        job = active_jobs[0]
        params = getattr(job, 'params', {}) or {}
        action = str(getattr(job, 'action_id', '') or '')
        source, target = str(params.get('src') or ''), str(params.get('dst') or '')
        pair = {'source': source, 'target': target} if source and target else None
        key = 'matching' if action == 'corpus.match-pair' else ''
        stage = next((item for item in result['stages'] if item.get('key') == key), None)
        if stage is not None:
            stage.update(
                jobId=getattr(job, 'id', ''), jobStatus=getattr(job, 'status', ''),
                currentAction=action or stage.get('currentAction', ''),
                startedAt=getattr(job, 'started_at', None) or stage.get('startedAt'),
            )
            if pair:
                stage.update(currentProgram=f"{source} → {target}", currentPair=pair)
                result.update(currentProgram=stage['currentProgram'], currentPair=pair)
            work_progress = _bounded_work_progress(getattr(job, 'work_progress', None))
            if work_progress:
                stage['workProgress'] = work_progress
            result['currentStage'] = stage.get('key', result.get('currentStage', ''))
            result['currentAction'] = stage.get('currentAction', result.get('currentAction', ''))
    return result


def list_runs(*, public: bool = False) -> list[dict[str, Any]]:
    """Observation never retires slots, creates directories, or repairs rows."""
    root = _directory().parent.resolve()
    rows = []
    try:
        paths = list(_directory().glob('*.json'))[:100]
    except OSError:
        paths = []
    for path in paths:
        try:
            row = _read(path.stem)
            _ensure_stages(row)
            command = _read_control(row['id'], root=root)
            for field in ('deadline', 'budgetSeconds', 'budgetOrigin'):
                if field in command:
                    row[field] = command[field]
            row['queuePriority'] = command.get('priority', row.get('queuePriority', 50))
            row['priorityReason'] = command.get('priorityReason', 'FIFO among projects with equal priority.')
            diagnostic = _DIAGNOSTICS.get((str(root), row['id']))
            if diagnostic:
                row['authorityObservation'] = copy.deepcopy(diagnostic)
            float(row.get('updatedAt') or 0)
            _admission_order(row)
            rows.append(row)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    rows.sort(key=lambda row: float(row.get('updatedAt') or 0), reverse=True)
    positions = {row['id']: index + 1 for index, row in enumerate(sorted(
        (row for row in rows if row.get('admissionPending')), key=_admission_order))}
    for row in rows:
        row['queuePosition'] = positions.get(row['id'])
    if not public:
        return rows
    from .actions.jobs import list_jobs
    live_jobs = list_jobs(compact=True)
    public_rows = []
    for row in rows:
        try:
            projected = _public_run(row, detailed=row.get('status') in {'running', 'queued', 'paused'}, live_jobs=live_jobs)
            if 'authorityObservation' in row:
                projected['authorityObservation'] = row['authorityObservation']
            public_rows.append(projected)
        except (ValueError, KeyError, TypeError, AttributeError):
            public_rows.append({'id': row['id'], 'status': 'unavailable', 'durable': False})
    return public_rows


def _admission_order(row: dict[str, Any]) -> tuple[int, float, str]:
    command = _read_control(row['id'])
    return (-int(command.get('priority', row.get('queuePriority', 50))), float(row.get('createdAt', 0)), row['id'])


def _inventory_directory():
    # Desired-state producers must not create an unqualified preparations tree.
    return _directory().parent / 'preparation-inventory-v1'


def _inventory_request(run_id: str, *, root: Path | None = None) -> dict[str, Any]:
    directories = (root / 'preparation-inventory-v1', root / 'preparations' / 'inventory') if root is not None else (_inventory_directory(), _directory() / 'inventory')
    for directory in directories:
        try:
            return _load_row(directory / (run_id + '.json'))
        except (OSError, ValueError):
            continue
    return {}


def inventory_changed(locator: str) -> dict[str, Any]:
    """Record independent desired state; this is not an authority capability."""
    context = _project_context({'locator': locator})
    run_id = _context_id(context)
    request = {'id': run_id, 'locator': context['locator'], 'generation': uuid.uuid4().hex, 'updatedAt': time.time()}
    directory = _inventory_directory()
    directory.mkdir(exist_ok=True)
    temporary = directory / (run_id + '.' + request['generation'] + '.tmp')
    temporary.write_text(json.dumps(request))
    temporary.replace(directory / (run_id + '.json'))
    _start_admission_worker()
    return {'id': run_id, 'status': 'accepted', 'inventoryGeneration': request['generation']}


def _eligible_probe(root, run_id):
    key = (str(root), run_id)
    if key in _SUSPENDED or key in _FAULTS or time.monotonic() < _NEXT_CONTROL_PROBE.get(key, 0):
        return False
    if key in _HEALTHY or run_id in _ACTIVE:
        return True
    return str(root) not in _NAMESPACE_LIMITS and str(root) not in _NAMESPACE_FAULTS and time.monotonic() >= _NEXT_NAMESPACE_PROBE.get(str(root), 0)


def _admit_entry(root, run_id, context):
    if not _eligible_probe(root, run_id):
        return
    if (str(root), run_id) not in _HEALTHY and run_id not in _ACTIVE:
        _NEXT_NAMESPACE_PROBE[str(root)] = time.monotonic() + 1
        while len(_NEXT_NAMESPACE_PROBE) > 100:
            _NEXT_NAMESPACE_PROBE.pop(next(iter(_NEXT_NAMESPACE_PROBE)))
    try:
        submit(context, resume=True, _admit=True)
    except _PreparationIssuanceWait as exc:
        _diagnostic(root, run_id, exc)
    except _PreparationControlWait as exc:
        _diagnostic(root, run_id, exc)
    except _PreparationAuthorityRefused as exc:
        _diagnostic(root, run_id, exc)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
        _diagnostic(root, run_id, _refusal(run_id, 'preparation_persistence_failed' if isinstance(exc, OSError) else 'preparation_continuity_required'))


def _collect_inventory_admissions() -> None:
    root = _directory().parent.resolve()
    paths = list(_inventory_directory().glob('*.json'))[:100] + list((_directory() / 'inventory').glob('*.json'))[:100]
    for path in paths:
        run_id = path.stem
        try:
            request = _load_row(path)
            if not _valid_id(request.get('id')) or not request.get('locator'):
                continue
            run_id = request['id']
            if not _eligible_probe(root, run_id) or run_id in _ACTIVE:
                continue
            try:
                row = _read(run_id)
            except FileNotFoundError:
                row = {}
            if row.get('inventoryGeneration') == request.get('generation'):
                continue
            command = _read_control(run_id, root=root, strict=True) if row else {}
            if command.get('operation') in {'pause', 'stop'} or row.get('status') == 'cancelled' or _budget_expired(command.get('deadline', row.get('deadline'))):
                continue
            _admit_entry(root, run_id, {'locator': request['locator']})
        except _PreparationIssuanceWait as exc:
            _diagnostic(root, run_id, exc)
        except _PreparationControlWait as exc:
            _diagnostic(root, run_id, exc)
        except _PreparationAuthorityRefused as exc:
            _diagnostic(root, run_id, exc)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            _diagnostic(root, run_id, _refusal(run_id, 'preparation_persistence_failed' if isinstance(exc, OSError) else 'preparation_continuity_required'))


def _start_admission_worker() -> None:
    global _ADMISSION_THREAD
    with _LOCK:
        if _ADMISSION_THREAD is None or not _ADMISSION_THREAD.is_alive():
            _ADMISSION_THREAD = threading.Thread(target=_drain_admissions, name='workflow-admission', daemon=True)
            _ADMISSION_THREAD.start()
    _ADMISSION_WAKE.set()


def _drain_admissions() -> None:
    while True:
        _ADMISSION_WAKE.wait(30)
        _ADMISSION_WAKE.clear()
        with _LOCK:
            waiting = list(_WAITING)
        root = _directory().parent.resolve()
        pending = []
        for run_id in waiting:
            if not _eligible_probe(root, run_id):
                continue
            try:
                row = _read(run_id)
                pending.append((_admission_order(row), row))
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                _diagnostic(root, run_id, _refusal(run_id, 'preparation_persistence_failed' if isinstance(exc, OSError) else 'preparation_continuity_required'))
        for _, row in sorted(pending, key=lambda item: item[0]):
            if len(_ACTIVE) >= 4:
                break
            _admit_entry(root, row['id'], {key: row.get(key, '') for key in ('locator', 'program', 'slug')})
        try:
            _collect_inventory_admissions()
        except (OSError, ValueError):
            # Namespace enumeration is unavailable; retained requests stay pending.
            continue


def _project_context(context: dict[str, Any]) -> dict[str, Any]:
    from agentdecompile_recovery.corpus.ghidra_project import classify_locator
    locator = str(context.get('locator') or '')
    if not locator:
        candidate = str(context.get('program') or '')
        if Path(candidate).is_absolute() and Path(candidate).suffix.lower() in {'.gpr', '.rep'}:
            project_info = classify_locator(candidate)
            if project_info.get('kind') == 'ghidra-project':
                locator = candidate
    info = classify_locator(locator) if locator else {}
    if info.get('kind') in {'ghidra-project', 'shared-project'}:
        locator = str(info.get('canonical') or locator)
        if info.get('gpr'):
            locator = str(Path(info['gpr']).resolve())
        return {**context, 'locator': locator, 'program': '', 'slug': ''}
    if locator and (locator.startswith('ghidra:') or Path(locator).suffix.lower() in {'.gpr', '.rep'} or Path(locator).is_dir()):
        return {**context, 'locator': locator, 'program': '', 'slug': ''}
    return dict(context)


def _without_backup_siblings(programs: list[str]) -> list[str]:
    """Exclude a ``.keep`` backup only when its canonical sibling exists.

    Ghidra projects sometimes retain ``program.keep`` alongside ``program``.
    It is a backup of the same project object, not another build variant.  Do
    not make a product-specific assumption: preserve a ``.keep`` entry when
    no base sibling is present, but never schedule both copies as distinct
    recovery targets.
    """
    known = {str(program).replace('\\', '/').casefold() for program in programs}
    return [
        program for program in programs
        if not (str(program).casefold().endswith('.keep') and str(program).replace('\\', '/').casefold()[:-5] in known)
    ]


def _execution_program_bindings(locator: str, info: dict[str, Any], programs: list[str], *, root: Path | None = None, db: Path | None = None) -> dict[str, tuple[str, str]]:
    """Route every shared-folder program to the Ghidra project that owns it.

    A shared repository is an inventory scope, not necessarily one local Ghidra
    project.  Choosing a single project with the largest overlap lets unrelated
    programs be sent to the wrong database.  Prefer durable import bindings;
    otherwise discover a local project containing the exact path or its unique
    leaf name.  An unresolved program is deliberately left without a route so
    the workflow reports the missing prerequisite instead of analyzing another
    binary by accident.
    """
    if str(info.get('kind') or '') != 'shared-fs':
        return {program: (locator, program) for program in programs}

    from agentdecompile_recovery.corpus.ghidra_project import inspect_locator, shared_defaults

    def normalized(value: str) -> str:
        return str(value or '').replace('\\', '/').strip().lstrip('/')

    program_paths = {
        str(name): normalized(str(path))
        for name, path in (info.get('program_paths') or {}).items()
        if name and path
    }
    # The filesystem inventory exposes short display names while repository
    # entries are folder-qualified DomainFile paths.  Keep the former as the
    # receipt key, but join it to the latter before comparing repositories.
    requested = {
        program: program_paths.get(str(program), program_paths.get(Path(str(program)).name, normalized(program)))
        for program in programs
    }

    def binding_matches_requested(source_key: str, actual: str) -> bool:
        """Reject an old binding when its selected Ghidra object is unrelated.

        ``program_binding`` predates shared-folder routing and can contain a
        source path paired with whichever program happened to be active.  Its
        locator alone is therefore not proof that the selected object is the
        same binary.  A local project often prefixes the imported filename
        (``NWN-Diamond__nwmain.exe``), so accept that harmless naming form but
        never let a Jade Empire source path select ``nwmain.exe``.
        """
        expected = Path(source_key).name.casefold()
        observed = Path(normalized(actual)).name.casefold()
        return bool(expected and observed and (observed == expected or observed.endswith(expected) or expected.endswith(observed)))

    bindings: dict[str, list[tuple[str, str]]] = {program: [] for program in programs}
    rows, _ = query_db('SELECT source_path, locator, program FROM program_binding ORDER BY updated DESC', db=db)
    for source, project_locator, project_program in rows:
        for program, source_key in requested.items():
            if normalized(str(source)) == source_key:
                bindings[program].append((str(project_locator), str(project_program)))

    # A filesystem repository is inventory, but its sibling server.log records
    # the endpoint that can open those exact folder-qualified DomainFiles. Prefer
    # that live project over stale local checkout bindings.
    defaults = shared_defaults()
    origin = info.get('origin') if isinstance(info.get('origin'), dict) else {}
    origin_repository = str(origin.get('repository') or '').strip()
    ports = [origin.get('port')]
    try:
        log_lines = (Path(locator) / 'server.log').read_text(errors='replace').splitlines()
        ports.extend(line.rsplit(':', 1)[-1].strip() for line in reversed(log_lines)
                     if 'RMI Registry port:' in line)
    except OSError:
        pass
    ports.append(defaults.get('port'))
    host = str(origin.get('host') or defaults.get('host') or '127.0.0.1')
    live_routes: dict[str, tuple[str, str]] = {}
    for repository in info.get('repositories') or []:
        if not isinstance(repository, dict):
            continue
        repository_name = str(repository.get('name') or '').strip()
        if origin_repository and repository_name.casefold() == origin_repository.casefold():
            repository_name = origin_repository
        repository_programs = {
            normalized(str(item.get('path') or f"{str(item.get('folder') or '/').rstrip('/')}/{item.get('name') or ''}")): str(item.get('path') or f"{str(item.get('folder') or '/').rstrip('/')}/{item.get('name') or ''}")
            for item in repository.get('programs') or [] if isinstance(item, dict)
        }
        if not repository_name or not set(requested.values()).intersection(repository_programs):
            continue
        for port in dict.fromkeys(ports):
            try:
                shared_locator = f'ghidra://{host}:{int(port)}/{repository_name}'
            except (TypeError, ValueError):
                continue
            try:
                live = inspect_locator(shared_locator)
            except (OSError, ValueError):
                continue
            if not live.get('reachable'):
                continue
            canonical = str(live.get('canonical') or shared_locator)
            for program, source_key in requested.items():
                if actual := repository_programs.get(source_key):
                    live_routes[program] = (canonical, actual)
            break

    candidates: list[str] = []
    for choices in bindings.values():
        candidates.extend(project for project, _ in choices)
    search_roots = (root,) if root is not None else (live_root(), _directory().parent)
    for search_root in search_roots:
        if search_root:
            base = Path(search_root)
            for pattern in ('workspace/*.gpr', 'native-checkouts/**/*.gpr', 'copied-projects/*.gpr', 'ghidra-projects/*.gpr'):
                found = [str(path.resolve()) for path in base.glob(pattern)]
                candidates.extend(found)

    available: dict[str, dict[str, str]] = {}
    for candidate in dict.fromkeys(item for item in candidates if item):
        try:
            discovered = inspect_locator(candidate)
        except (OSError, ValueError):
            continue
        # A shared folder supplies inventory only.  The executor must receive
        # a concrete local Ghidra project; otherwise ensure_project may select
        # a sibling .gpr with a misleading partial overlap.
        if str(discovered.get('kind') or '') != 'ghidra-project':
            continue
        listed = [str(item) for item in discovered.get('programs') or []]
        if listed:
            available[candidate] = {normalized(item): item for item in listed}

    routes: dict[str, tuple[str, str]] = {}
    for program, source_key in requested.items():
        if program in live_routes:
            routes[program] = live_routes[program]
            continue
        # Without a live server route, reuse a previous successful import when
        # the project still contains that program.
        for candidate, bound_program in bindings[program]:
            programs_by_path = available.get(candidate, {})
            actual = programs_by_path.get(normalized(bound_program))
            if actual and binding_matches_requested(source_key, actual):
                # The Ghidra session accepts the program path recorded in its
                # own project inventory.  A shared-folder path may carry a
                # grouping prefix (for example ``/TSL/...``) that is absent
                # from a native checkout, and passing that prefix causes the
                # session resolver to reject the program before analysis can
                # begin.  The binding has already proved the source identity;
                # use the exact stored project path to select that object.
                routes[program] = (candidate, actual)
                break
        if program in routes:
            continue
        exact: list[tuple[str, str]] = []
        leaf: list[tuple[str, str]] = []
        wanted_leaf = Path(source_key).name
        for candidate, programs_by_path in available.items():
            actual = programs_by_path.get(source_key)
            if actual:
                exact.append((candidate, actual))
            for discovered_key, discovered in programs_by_path.items():
                if Path(discovered_key).name == wanted_leaf:
                    leaf.append((candidate, discovered))
        if len(exact) == 1:
            candidate, actual = exact[0]
            routes[program] = (candidate, actual)
        elif len(leaf) == 1:
            candidate, actual = leaf[0]
            routes[program] = (candidate, actual)
        elif exact:
            # Equivalent copies are safe to choose only when the local path is
            # deterministic.  Never choose a merely-largest unrelated project.
            candidate, actual = sorted(exact)[0]
            routes[program] = (candidate, actual)
        elif leaf:
            candidate, actual = sorted(leaf)[0]
            routes[program] = (candidate, actual)
        else:
            routes[program] = ('', '')
    return routes


def _supersede_obsolete_probe_routes(row: dict[str, Any], routes: dict[str, tuple[str, str]]) -> str:
    """Keep historical probe receipts while making a repaired route executable.

    Preparation used to send a shared project's display leaf (for example,
    ``JadeEmpire.exe``) to a session that can only resolve the qualified
    DomainFile path (``/JE/JadeEmpire.exe``).  A failed automatic probe is an
    audit record, not a reason to keep retrying its obsolete route.  Route
    revision is deliberately limited to read-only probes; analysis and other
    mutations keep their ordinary durable replay rules.
    """
    current = {
        program: {'locator': locator, 'program': target}
        for program, (locator, target) in sorted(routes.items())
        if locator and target
    }
    revision = hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest()
    targets = {details['program']: details for details in current.values()}
    by_leaf = {Path(details['program']).name: details for details in current.values()}
    changed = 0
    for receipt in (row.get('actions') or {}).values():
        if not isinstance(receipt, dict) or receipt.get('action') != 'mcp.execute-script':
            continue
        fields = receipt.get('params') or {}
        if not fields.get('_preparationProbe'):
            continue
        requested = str(fields.get('programPath') or '')
        expected = targets.get(requested) or by_leaf.get(Path(requested).name)
        prior_replacement = receipt.get('supersededByRoute') or {}
        if (not expected or receipt.get('executionRouteRevision') == revision
                or (isinstance(prior_replacement, dict) and prior_replacement.get('revision') == revision)):
            continue
        receipt.update(
            supersededAt=time.time(),
            supersededReason='A canonical shared-project execution route replaced this automatic probe receipt.',
            supersededByRoute={**expected, 'revision': revision},
        )
        changed += 1
    if changed:
        row.setdefault('events', []).append({
            'at': time.time(), 'stage': 'inspect',
            'message': f'Recorded {changed} historical probe receipt(s); canonical shared paths will be probed again.',
        })
        row['events'] = row['events'][-250:]
    row['executionRouteRevision'] = revision
    return revision


def _context_id(context: dict[str, Any], *, db: Path | None = None) -> str:
    key = json.dumps([str(db if db is not None else live_db()), str(context.get('locator') or ''), str(context.get('program') or ''), str(context.get('slug') or '')])
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def submit(context: dict[str, Any], *, resume: bool = False, _admit: bool = False) -> dict[str, Any]:
    if not isinstance(resume, bool):
        raise ValueError('resume must be a boolean')
    context = _project_context(context)
    if not context.get('locator') and not context.get('slug'):
        raise ValueError('Open a project or select a registered binary first.')
    selected_db = live_db()
    root, db = _directory().parent.resolve(), Path(selected_db).resolve()
    # Objective identity preserves the selected path's established spelling;
    # only physical execution uses the resolved path. Inventory uses the same key.
    run_id = _context_id(context, db=selected_db)
    key = (str(root), run_id)
    with _LOCK:
        current = _AUTHORITIES.get(run_id)
    if current is not None:
        with current.gate:
            if current.root != root or current.state != 'current':
                raise _refusal(run_id, authority=current)
            _check(current)
            return copy.deepcopy(current.committed)
    if key in _SUSPENDED or key in _FAULTS:
        raise _refusal(run_id)
    witness = _HEALTHY.get(key)
    birth = None
    if witness is None:
        # Acquisition and contention handling precede all execution slots/gates.
        birth = _issue_new_objective(root, run_id)
    try:
        authority = _acquire_authority(root, db, run_id, birth=birth)
    except _PreparationAuthorityRefused as exc:
        if exc.decision.get('leaseBusy'):
            with _LOCK:
                current = _AUTHORITIES.get(run_id)
            if current is not None and current.root == root:
                with _guard(current):
                    if current.committed is not None:
                        return copy.deepcopy(current.committed)
        raise
    try:
        with _guard(authority, phase='initialization'):
            row = authority.row
            if birth is not None:
                row.update(locator=str(context.get('locator') or ''), program=str(context.get('program') or ''),
                    slug=str(context.get('slug') or ''), status='queued',
                    scope='project' if context.get('locator') and not context.get('program') else 'binary',
                    createdAt=time.time(), workflowVersion=VERSION, budgetSeconds=DEFAULT_BUDGET_SECONDS,
                    deadline=None, budgetOrigin='default', queuePriority=50, actions={}, jobTimingContexts={},
                    retryDecisions={}, events=[], programs=[], checkpoints={}, stages=_merge_stages({}))
                admission_budget.initialize(row, context.get('maxActionAdmissions'))
                mcp_budget.initialize(row, context.get('maxMcpToolCalls'))
            elif not resume:
                return copy.deepcopy(row)
            command = _read_control(run_id, root=root, strict=True)
            for field in ('deadline', 'budgetSeconds', 'budgetOrigin'):
                if field in command:
                    row[field] = command[field]
            row.update(ownerHost=authority.owner[0], ownerPid=authority.owner[1], ownerStart=authority.owner[2],
                       queuePriority=command.get('priority', row.get('queuePriority', 50)),
                       inventoryGeneration=_inventory_request(run_id, root=root).get('generation'))
            _ensure_stages(row)
            if resume:
                _reset_resume_projection(row)
            if command.get('operation') in {'pause', 'stop'} or _budget_expired(row.get('deadline')):
                row.update(status='paused' if command.get('operation') == 'pause' else 'cancelled' if command.get('operation') == 'stop' else 'budget-stop', admissionPending=command.get('operation') == 'pause')
                _write(row, authority=authority, phase='initialization')
                if not row['admissionPending']:
                    with _LOCK:
                        _WAITING.discard(run_id)
                return copy.deepcopy(row)
            with _LOCK:
                queued = len(_ACTIVE) >= 4 or bool(_WAITING and not _admit)
                if not queued:
                    slot = _ExecutionSlot(authority)
                    authority.slot = slot
                    _ACTIVE[run_id] = slot
            if queued:
                row.update(status='queued', admissionPending=True, reason='Waiting for another project operation to release a worker.')
                _write(row, authority=authority, phase='initialization')
                with _LOCK:
                    _WAITING.add(run_id)
                _start_admission_worker()
                return copy.deepcopy(row)
            row.update(status='queued', admissionPending=False)
            with _LOCK:
                _WAITING.discard(run_id)
            # Independent root intent; it does not consume a child-action budget.
            row['rootHandoff'] = {'intentId': slot.intent, 'generation': authority.generation, 'status': 'intent'}
            _write(row, authority=authority, phase='intent')
            from .actions import jobs
            from .actions.catalog import action_by_id
            spec = action_by_id('workbench.prepare')
            if spec is None:
                raise ValueError('Preparation action is unavailable.')
            _check(authority, dispatch=True, phase='handoff')
            command = _read_control(run_id, root=root, strict=True)
            if command.get('operation') in {'pause', 'stop'} or _budget_expired(command.get('deadline', row.get('deadline'))):
                row.update(status='paused' if command.get('operation') == 'pause' else 'budget-stop')
                _write(row, authority=authority)
                return copy.deepcopy(row)
            try:
                job = jobs.STORE.start(spec, {'locator': row['locator'], 'program': row['program'], 'slug': row['slug'], 'preparation_id': run_id}, ['workbench.prepare'], preparation_authority=authority)
                row['jobId'] = job.id
                row['rootHandoff'].update(status='accepted', jobId=job.id)
                _write(row, authority=authority, phase='acknowledgement')
            except (_PreparationIssuanceWait, _PreparationControlWait):
                raise
            except Exception as exc:
                if isinstance(exc, (_PreparationIssuanceWait, _PreparationControlWait, _PreparationAuthorityRefused)):
                    refusal = exc
                else:
                    refusal = _refusal(run_id, 'preparation_continuity_required', 'handoff', authority,
                        'Root start outcome requires reconciliation.' if slot.worker_start_attempted else 'Root admission failed before any worker-start attempt.')
                _poison(authority, refusal)
                raise refusal from exc
            return copy.deepcopy(row)
    except (_PreparationIssuanceWait, _PreparationControlWait, _PreparationAuthorityRefused):
        raise
    except OSError as exc:
        refusal = _refusal(run_id, 'preparation_persistence_failed', 'initialization', authority)
        _poison(authority, refusal)
        raise refusal from exc
    finally:
        slot = authority.slot
        if slot is None or not slot.worker_start_attempted:
            _retire_capacity(slot)
            _release_lease(run_id, expectedAuthority=authority)


def _snapshot(authority):
    with _guard(authority):
        return copy.deepcopy(authority.row)


def _workflow_mutator(authority):
    """Named bounded edits only. No caller-supplied code executes under the gate."""
    checkpoint_fields = {
        'knowledge': {'knowledgeCursor', 'knowledgeComplete', 'knowledgeAvailable', 'knowledgeFingerprint', 'knowledgeDb', 'programFingerprint'},
        'target-image': {'targetImage'}, 'toolchain': {'toolchain'},
    }
    def mutate_state(expectedBasis, operation):
        basis, operation = copy.deepcopy(expectedBasis), copy.deepcopy(operation)
        with _guard(authority):
            row = authority.row
            program, family = basis.get('program'), basis.get('family')
            checkpoint = row.get('checkpoints', {}).get(program, {}) if program else None
            if program and checkpoint.get('programFingerprint') != basis.get('fingerprint'):
                refusal = _refusal(authority.run_id, authority=authority, reason='Workflow fingerprint basis changed.')
                _poison(authority, refusal)
                raise refusal
            if program and 'recoveryFamily' in basis and checkpoint.get('recoveryFamily') != basis['recoveryFamily']:
                refusal = _refusal(authority.run_id, authority=authority, reason='Workflow family selection changed.')
                _poison(authority, refusal)
                raise refusal
            if family and not program and basis.get('fingerprints') != {p: row.get('checkpoints', {}).get(p, {}).get('programFingerprint') for p in basis.get('fingerprints', {})}:
                refusal = _refusal(authority.run_id, authority=authority, reason='Workflow family basis changed.')
                _poison(authority, refusal)
                raise refusal
            if family and not program and 'programs' in basis:
                existing_family = row.get('recoveryFamilies', {}).get(family, {})
                if existing_family.get('programs', basis['programs']) != basis['programs']:
                    refusal = _refusal(authority.run_id, authority=authority, reason='Workflow family membership changed.')
                    _poison(authority, refusal)
                    raise refusal
            name = operation.get('name')
            if program and name in {*checkpoint_fields, 'workflow-init', 'stage-outcome', 'progress-file'}:
                checkpoint = row.setdefault('checkpoints', {}).setdefault(program, {})
            values, remove = operation.get('values', {}), operation.get('remove', [])
            if name == 'stage-update':
                key = operation['stage']
                status, reason = operation['status'], operation.get('reason', '')
                stage = next((item for item in row['stages'] if item['key'] == key), None)
                if stage is None:
                    title = next((name for item, name in _STAGES if item == key), key)
                    stage = {'key': key, 'title': title, 'status': 'queued', 'completed': 0, 'total': None, 'reason': ''}
                    row['stages'].append(stage)
                # A new accepted child supersedes an earlier retry/backoff note.
                # Leaving the old fallback on a running stage made the frontend
                # describe a previous failure instead of the operation in flight.
                if status == 'running':
                    stage.pop('nextFallback', None)
                    stage.pop('retryAt', None)
                    for retry_field in ('nextAction', 'wakeCondition', 'retryDecision'):
                        stage.pop(retry_field, None)
                    # Starting an unlimited child must not inherit a limit from
                    # a prior bounded probe or legacy execution attempt.
                    if values.get('jobId') and 'executionLimitSeconds' not in values:
                        stage.pop('executionDeadlineAt', None)
                        stage.pop('executionLimitSeconds', None)
                stage.update(status=status, reason=reason, **copy.deepcopy(values))
                # A completed/partial terminal must not keep rendering its last
                # child as an active stage. Preserve the link for the activity
                # inspector, but remove it from the live-stage projection.
                if status in {'completed', 'partial', 'blocked', 'cancelled'} and 'jobId' not in values:
                    if stage.get('jobId'):
                        stage['lastJobId'] = stage['jobId']
                    stage.pop('jobId', None)
                    stage.pop('jobStatus', None)
                row.update(currentStage=key, currentProgram=values.get('currentProgram', stage.get('currentProgram', '')), currentAction=values.get('currentAction', stage.get('currentAction', '')))
                if reason:
                    row['events'].append({'at': time.time(), 'stage': key, 'message': reason})
                    row['events'] = row['events'][-250:]
                selected = stage
            elif name in checkpoint_fields and program:
                allowed = checkpoint_fields[name]
                if not set(values) <= allowed or not set(remove) <= allowed:
                    raise ValueError('Unsupported workflow checkpoint edit')
                for field in remove:
                    checkpoint.pop(field, None)
                checkpoint.update(values)
                selected = checkpoint
            elif name == 'workflow-init' and program:
                checkpoint.setdefault('workflow', {})
                selected = checkpoint
            elif name == 'stage-outcome' and program and operation.get('stage') in {key for key, _ in RECOVERY_STAGES}:
                checkpoint.setdefault('workflow', {})[operation['stage']] = values
                selected = checkpoint
            elif name == 'progress-file' and program:
                if operation.get('clear'):
                    if row.get('functionProgressFile') != operation.get('path'):
                        raise _refusal(authority.run_id, authority=authority, reason='Progress attempt changed.')
                    row.pop('functionProgressFile', None)
                else:
                    row['functionProgressFile'] = operation['path']
                selected = checkpoint
            elif name in {'family-init', 'family-finalize'} and family:
                if not set(values) <= {'family', 'programs', 'eligiblePrograms', 'state', 'updatedAt', 'reason', 'outcomes'}:
                    raise ValueError('Unsupported family edit')
                selected = row.setdefault('recoveryFamilies', {}).setdefault(family, {})
                selected.update(values)
            else:
                raise ValueError('Unsupported workflow mutation')
            _write(row, authority=authority)
            return copy.deepcopy(selected)
    return mutate_state


def execute(params: dict[str, Any], cancel: threading.Event, *, authority) -> tuple[int, str]:
    from .actions import jobs
    from agentdecompile_recovery.corpus.ghidra_project import inspect_locator

    run_id = params['preparation_id']
    if not isinstance(authority, _PreparationAuthority):
        raise _refusal(run_id, 'preparation_authority_lost')
    with _guard(authority, dispatch=True):
        if authority.run_id != run_id:
            refusal = _refusal(authority.run_id, authority=authority)
            _poison(authority, refusal)
            raise refusal
        row = authority.row
        _ensure_stages(row)
        row['status'] = 'running'
        _write(row, authority=authority)
    comparison_inputs: dict[str, Any] = {}
    issuance_wait = False

    mutate_state = _workflow_mutator(authority)

    def update(key: str, status: str, reason: str = '', **values: Any) -> None:
        mutate_state({}, {'name': 'stage-update', 'stage': key, 'status': status,
                          'reason': reason, 'values': values})

    def guarded_probe(operation, *args):
        with _guard(authority):
            return operation(*args)

    def stopped() -> bool:
        command = _read_control(run_id, root=authority.root, strict=True)
        if 'deadline' in command:
            with _guard(authority):
                row['deadline'] = command['deadline']
                row['budgetSeconds'] = command.get('budgetSeconds', row['budgetSeconds'])
        while command.get('operation') == 'pause' and not cancel.is_set():
            with _guard(authority):
                row['status'] = 'paused'
            _write(row, authority=authority)
            if _budget_expired(row.get('deadline')):
                return True
            cancel.wait(1)
            command = _read_control(run_id, root=authority.root, strict=True)
            if 'deadline' in command:
                with _guard(authority):
                    row.update(deadline=command['deadline'], budgetSeconds=command.get('budgetSeconds', row['budgetSeconds']))
        if row['status'] == 'paused':
            with _guard(authority):
                row['status'] = 'running'
            _write(row, authority=authority)
        if command.get('operation') == 'stop':
            cancel.set()
        return cancel.is_set() or _budget_expired(row.get('deadline'))

    def pause_outcome(job_id: str = '') -> dict[str, Any]:
        """Checkpoint a matching wave without cancelling its accepted child."""
        return {
            'ok': False,
            'paused': True,
            'jobId': job_id,
            'error': 'Pause requested. No additional comparison was admitted.',
        }

    def action(key: str, name: str, fields: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        # Admission and terminal receipts are durable. An uncertain external
        # mutation is blocked after owner death rather than replayed blindly.
        probe = bool(fields.get('_preparationProbe')) or name == 'workbench.merge-evidence'
        retry_revision = _retry_input_revision(name, fields)
        identity_parts = [name, fields, retry_revision, context.get('locator'), context.get('program'),
                          context.get('slug'), row['checkpoints'].get(context.get('program', ''), {}).get('programFingerprint')]
        # Automatic probes do not mutate Ghidra.  Bind their durable action
        # identity to the route revision so a repaired shared DomainFile path
        # gets one fresh observation instead of inheriting a failed leaf-path
        # receipt from an older execution route.
        if fields.get('_preparationProbe'):
            identity_parts.append(row.get('executionRouteRevision', ''))
        retry_basis = None
        if name == 'corpus.match-pair':
            retry_basis = _comparison_inventory(str(fields.get('src') or ''), str(fields.get('dst') or ''), comparison_inputs)
            identity_parts.append(retry_basis)
        identity = json.dumps(identity_parts, sort_keys=True)
        action_id = hashlib.sha256(identity.encode()).hexdigest()
        with _guard(authority):
            history = row.setdefault('actions', {})
            prior = (_matching_retry_prior(history, action_id, fields) if name == 'corpus.match-pair'
                     else copy.deepcopy(history.get(action_id, {})))
        if prior.get('status') == 'ok' and not (prior.get('result') or {}).get('ownershipUnresolved') and (probe or key in {'facts', 'calibrate-global', 'verify-byte-accuracy'}):
            prior = {}
        if not probe and prior.get('status') == 'ok' and not (prior.get('result') or {}).get('ownershipUnresolved') and key not in {'facts', 'calibrate-global', 'verify-byte-accuracy'}:
            return copy.deepcopy(prior['result'])
        # A successful observation may be refreshed; failed/uncertain attempts
        # retain their spending. Relevant input changes already change action_id.
        prior = _action_prior_for_retry(name, prior)
        prior_job = jobs.get_job(prior.get('jobId', '')) if prior.get('jobId') else None
        unsettled = (prior.get('status') in {'submitting', 'queued', 'running', 'interrupted', 'cancelling'}
                     or bool((prior.get('result') or {}).get('unknownOutcome'))
                     or bool((prior.get('result') or {}).get('ownershipUnresolved')))
        if unsettled and prior_job is not None and prior_job.status in {'ok', 'failed', 'cancelled'}:
            # A terminal job receipt closes the dispatch/recording crash gap.
            # Reconcile it instead of launching the same accepted action again.
            terminal_data = _decode_job_output(prior_job.log or '')
            terminal_outcome = {
                'ok': prior_job.status == 'ok', 'data': terminal_data,
                'log': (prior_job.log or '')[-4000:], 'jobId': prior_job.id,
                'finishedAt': prior_job.finished_at, 'error': prior_job.error,
                'ownershipUnresolved': getattr(prior_job, 'resource_disposition', '') == 'quarantined' or _unresolved_job_ownership(terminal_data, prior.get('result')),
                'unknownOutcome': bool((prior.get('result') or {}).get('unknownOutcome')) and terminal_data is None,
            }
            prior.update(status='ok' if terminal_outcome['ok'] else 'failed', result=terminal_outcome)
            with _guard(authority):
                history[action_id] = prior
                _write(row, authority=authority)
            if terminal_outcome['ok'] and not terminal_outcome['ownershipUnresolved'] and not terminal_outcome['unknownOutcome']:
                return terminal_outcome
        available = bool(prior_job is not None and not getattr(prior_job, 'history_only', False)
                         and not getattr(prior_job, 'owner_unavailable', False)
                         and prior_job.status in {'queued', 'running', 'cancelling'})
        previous_provider = (prior.get('result') or {}).get('data') or {}
        provider_revised = (isinstance(previous_provider, dict)
            and previous_provider.get('nextAction') == 'provider_budget_exhausted'
            and mcp_budget.initialize(row)['allocationRevision'] > previous_provider.get('allocationRevision', 0))
        decision = decide_retry(
            prior, transient=transient_failure(prior.get('result', {})),
            prerequisite_recovered=bool(prior.get('retryPrerequisiteRecovered')) or provider_revised,
            owner_available=available,
        )
        if name.startswith('mcp.') and decision['nextAction'] not in {'unknown_outcome', 'await_existing', 'reuse_result'}:
            decision = mcp_budget.exhausted(row) or decision
        with _guard(authority):
            history.setdefault(action_id, dict(prior))['retryDecision'] = decision
            if retry_basis is not None:
                history[action_id].update(action=name, params=fields, retryBasis=retry_basis)
            _remember_retry_decision(row, action_id, name, decision)
            _write(row, authority=authority)
        if decision['nextAction'] != 'dispatch':
            update(key, 'waiting' if available else 'blocked', decision['reason'],
                   nextAction=decision['nextAction'], wakeCondition=decision['wakeCondition'],
                   retryDecision=decision, attempts=decision['attemptsSpent'])
            return refusal_outcome(prior, decision)
        for attempt in range(int(prior.get('attempts', 0)), MAX_ACTION_ATTEMPTS):
            # Matching submits several independent candidates into the shared
            # job store. A pause must freeze that admission queue, while a
            # child already executing gets to write its durable receipt.
            if name == 'corpus.match-pair' and _read_control(run_id, root=authority.root, strict=True).get('operation') == 'pause':
                return pause_outcome()
            if stopped():
                raise InterruptedError('Workflow stopped or its execution budget was reached.')
            with _guard(authority):
                provider_decision = mcp_budget.exhausted(row) if name.startswith('mcp.') else None
                if provider_decision:
                    _remember_retry_decision(row, action_id, name, provider_decision)
                    _write(row, authority=authority)
                    update(key, 'blocked', provider_decision['reason'], nextAction=provider_decision['nextAction'], wakeCondition=provider_decision['wakeCondition'], retryDecision=provider_decision)
                    return refusal_outcome(prior, provider_decision)
                dispatch_id = uuid.uuid4().hex
                objective_decision = admission_budget.reserve(row, dispatch_id, action_id, name)
                if objective_decision['nextAction'] != 'dispatch':
                    history.setdefault(action_id, {})['retryDecision'] = objective_decision
                    _remember_retry_decision(row, action_id, name, objective_decision)
                    _write(row, authority=authority)
                    update(key, 'blocked', objective_decision['reason'],
                           nextAction=objective_decision['nextAction'],
                           wakeCondition=objective_decision['wakeCondition'], retryDecision=objective_decision)
                    return refusal_outcome(prior, objective_decision)
                history[action_id] = {
                    'dispatchId': dispatch_id,
                    'status': 'submitting', 'action': name, 'params': copy.deepcopy(fields),
                    'target': context.get('program') or context.get('locator'),
                    **({'retryBasis': retry_basis} if retry_basis is not None else {}),
                    'attempts': attempt + 1, 'at': time.time(),
                    'retryDecision': {**decision, 'attemptsSpent': attempt + 1,
                                      'attemptsRemaining': MAX_ACTION_ATTEMPTS - attempt - 1},
                    **({'executionRouteRevision': row.get('executionRouteRevision', ''),
                        'executionRoute': {'locator': context.get('locator', ''), 'program': context.get('program', '')}}
                       if fields.get('_preparationProbe') else {}),
                }
                _remember_retry_decision(row, action_id, name, history[action_id]['retryDecision'])
                _write(row, authority=authority, phase='intent')
            mcp_reserve = _mcp_reservation_capability(authority, dispatch_id=dispatch_id, action_id=action_id)
            job_fields = dict(fields)
            if name == 'corpus.match-pair':
                # This records the project's explicit budget decision with
                # the child receipt. The subprocess remains cancellable; only
                # an Unlimited project avoids the generic 30-minute cutoff.
                job_fields['_preparationUnlimited'] = row.get('deadline') is None
                job_fields['progress_json'] = True
            def start_child():
                if key == 'facts' and name == 'mcp.execute-script':
                    return jobs._start_preparation_facts_inventory(job_fields, context, _mcp_reserve=mcp_reserve, _execution_context=authority)
                elif fields.get('_preparationProbe') and name == 'mcp.execute-script':
                    return jobs._start_preparation_probe(job_fields, context, _mcp_reserve=mcp_reserve, _execution_context=authority)
                else:
                    return jobs.start_job(name, job_fields, context=context, confirm=True, _execution_context=authority, **({"_mcp_reserve": mcp_reserve} if name.startswith("mcp.") else {}))
            response, status = _handoff(authority, dispatch_id, start_child)
            if status >= 400:
                outcome = {'ok': False, 'error': response.get('error')}
            else:
                job_id = response['job']['id']
                with _guard(authority):
                    admission_budget.acknowledge(row, dispatch_id, job_id)
                    history[action_id].update(status='queued', jobId=job_id)
                    checkpoint = row['checkpoints'].get(context.get('program', ''), {})
                    row.setdefault('jobTimingContexts', {})[job_id] = {key: checkpoint.get(key) for key in ('architecture', 'ghidraVersion', 'workSize', 'toolchain')}
                    row['jobTimingContexts'][job_id].update(actionId=name, createdAt=time.time())
                    _write(row, authority=authority, phase='acknowledgement')
                target = str(fields.get('programPath') or fields.get('program') or context.get('program') or fields.get('src') or context.get('locator') or '')
                update(key, 'running', f'{name}: {target}' if target else name, jobId=job_id,
                       lastJobId=job_id, currentProgram=target, currentAction=name,
                       jobStatus=response['job'].get('status', 'queued'), startedAt=time.time(), attempts=attempt + 1)
                previous_status = None
                # A Ghidra analysis can legitimately run for a long time
                # without changing the job's coarse status.  Persist a small
                # heartbeat so the durable run and reconnecting clients can
                # distinguish active work from a stale receipt without
                # rewriting it on every 250 ms poll.
                last_heartbeat_at = 0.0
                wait_limit = float(fields.get('workflowWaitSeconds') or (900 if probe else 0))
                wait_deadline = time.monotonic() + wait_limit if wait_limit else None
                if wait_limit:
                    # This is an execution bound, not a completion ETA.  The
                    # UI uses it to distinguish an active bounded operation
                    # from an unbounded spinner.
                    update(key, 'running', executionDeadlineAt=time.time() + wait_limit,
                           executionLimitSeconds=int(wait_limit))
                while True:
                    job = jobs.get_job(job_id)
                    progress_path = row.get('functionProgressFile')
                    if progress_path:
                        from .workflow import read_object
                        work_progress = read_object(Path(progress_path))
                        stage = next(item for item in row['stages'] if item['key'] == key)
                        if work_progress and work_progress != stage.get('workProgress'):
                            update(key, 'running', workProgress=work_progress)
                    if name == 'corpus.match-pair' and isinstance(getattr(job, 'work_progress', None), dict):
                        stage = next(item for item in row['stages'] if item['key'] == key)
                        if job.work_progress != stage.get('workProgress'):
                            update(key, 'running', workProgress=dict(job.work_progress))
                    command = _read_control(run_id, root=authority.root, strict=True)
                    if name == 'corpus.match-pair' and command.get('operation') == 'pause':
                        if job is not None and job.status == 'running':
                            # The active pair owns durable comparison output. Let
                            # it finish, then checkpoint the wave before another
                            # queued pair can begin. Persist this transition once;
                            # the normal heartbeat remains responsible for liveness.
                            stage = next(item for item in row['stages'] if item['key'] == key)
                            if not stage.get('pauseRequestedAt'):
                                update(key, 'running', 'Pause requested. Finishing the accepted comparison before checkpointing.',
                                       jobId=job_id, currentProgram=target, currentAction=name,
                                       jobStatus='running', pauseRequestedAt=time.time())
                        else:
                            # This candidate never began execution. Remove it
                            # from the shared queue so the completed sibling is
                            # the last admitted comparison in this paused wave.
                            _cancel_child(authority, dispatch_id, job_id, jobs.cancel_job)
                            drain_deadline = time.monotonic() + 120
                            while job is not None and job.status in {'queued', 'running', 'cancelling'}:
                                if time.monotonic() > drain_deadline:
                                    raise InterruptedError('Queued comparison did not drain while honoring pause.')
                                time.sleep(.25)
                                job = jobs.get_job(job_id)
                            outcome = pause_outcome(job_id)
                            with _guard(authority):
                                history[action_id].update(status='paused', result=copy.deepcopy(outcome))
                                _write(row, authority=authority)
                            return outcome
                    elif stopped():
                        _cancel_child(authority, dispatch_id, job_id, jobs.cancel_job)
                        update(key, 'cancelling', 'Waiting for the accepted operation to stop before releasing project ownership.')
                        drain_deadline = time.monotonic() + 120
                        while job is not None and job.status in {'queued', 'running', 'cancelling'}:
                            if time.monotonic() > drain_deadline:
                                raise InterruptedError('Workflow stop timed out waiting for child job to cancel.')
                            time.sleep(.25)
                            job = jobs.get_job(job_id)
                        raise InterruptedError('Workflow stopped after its accepted operation drained.')
                    if job is None:
                        outcome = {'ok': False, 'error': 'The accepted stage job is unavailable; output reconciliation is required.', 'jobId': job_id, 'unknownOutcome': True}
                        break
                    if wait_deadline is not None and time.monotonic() >= wait_deadline:
                        _cancel_child(authority, dispatch_id, job_id, jobs.cancel_job)
                        drain_deadline = time.monotonic() + 30
                        while job is not None and job.status in {'queued', 'running', 'cancelling'} and time.monotonic() < drain_deadline:
                            cancel.wait(.25)
                            job = jobs.get_job(job_id)
                        if job is None or job.status in {'queued', 'running', 'cancelling', 'interrupted'}:
                            outcome = {
                                'ok': False,
                                'error': f'{key}-timeout: cancellation did not reach a terminal state; project ownership is quarantined and this operation will not be retried.',
                                'jobId': job_id,
                                'ownershipUnresolved': True,
                                'unknownOutcome': job is None or job.status == 'interrupted',
                            }
                        else:
                            outcome = {'ok': False, 'error': f'{key}-timeout: the {"read-only probe" if probe else "bounded operation"} exceeded {int(wait_limit)} seconds and drained after cancellation.', 'jobId': job_id}
                        break
                    if job.status != previous_status:
                        previous_status = job.status
                        with _guard(authority):
                            history[action_id]['status'] = job.status
                        update(key, 'running', jobStatus=job.status, lastJobUpdateAt=time.time())
                    now = time.time()
                    if job.status in {'queued', 'running', 'cancelling'} and now - last_heartbeat_at >= 10:
                        last_heartbeat_at = now
                        update(key, 'running', jobStatus=job.status, lastJobUpdateAt=now,
                               heartbeatAt=now)
                    if job.status not in {'queued', 'running', 'cancelling'}:
                        text = job.log.strip()
                        data = _decode_job_output(text)
                        with _guard(authority):
                            row['jobTimingContexts'][job_id].update(status=job.status, startedAt=job.started_at, finishedAt=job.finished_at)
                        outcome = {'ok': job.status == 'ok', 'data': data, 'log': text[-4000:], 'jobId': job_id, 'finishedAt': job.finished_at, 'error': job.error, 'unknownOutcome': job.status == 'interrupted', 'ownershipUnresolved': getattr(job, 'resource_disposition', '') == 'quarantined' or _unresolved_job_ownership(data)}
                        break
                    cancel.wait(.25)
            with _guard(authority):
                history[action_id].update(status='ok' if outcome['ok'] else 'failed', result=copy.deepcopy(outcome))
                _write(row, authority=authority)
            provider_decision = outcome.get('data')
            if isinstance(provider_decision, dict) and str(provider_decision.get('nextAction', '')).startswith('provider_'):
                decision = {k: provider_decision[k] for k in ('nextAction', 'reason', 'wakeCondition', 'attemptsSpent', 'attemptsRemaining', 'allocationRevision') if k in provider_decision}
                decision.setdefault('attemptsSpent', mcp_budget.initialize(row)['consumed'])
            else:
                decision = decide_retry(history[action_id], transient=transient_failure(outcome))
            with _guard(authority):
                history[action_id]['retryDecision'] = copy.deepcopy(decision)
                _remember_retry_decision(row, action_id, name, decision)
                _write(row, authority=authority)
            if outcome['ok'] and decision['nextAction'] == 'reuse_result':
                return outcome
            if decision['nextAction'] != 'dispatch':
                update(key, 'blocked', decision['reason'], nextAction=decision['nextAction'],
                       wakeCondition=decision['wakeCondition'], retryDecision=decision,
                       attempts=decision['attemptsSpent'])
                return {**outcome, 'ok': False, 'retryDecision': decision, 'nextAction': decision['nextAction'],
                        'wakeCondition': decision['wakeCondition'], 'error': decision['reason'],
                        'previousError': outcome.get('error', '')}
            delay = 2 ** (attempt + 1)
            update(key, 'waiting', f'Temporary service failure. Another attempt follows in {delay} seconds.', attempts=attempt + 1, nextFallback='Retry transient service failure', retryAt=time.time() + delay)
            if cancel.wait(delay):
                raise InterruptedError('Workflow stopped during service backoff.')
        return refusal_outcome(prior, decide_retry(prior))

    try:
        locator, selected = row['locator'], row['program']
        info = inspect_locator(locator) if locator else {'ok': True, 'programs': []}
        if not info.get('ok'):
            raise ValueError(info.get('error') or 'The project could not be inspected.')
        # Shared repositories can contain several objects with the same leaf
        # name.  Ghidra resolves the folder-qualified path unambiguously;
        # using a leaf here sent preparation to an arbitrary object (or no
        # object) and made a moved external source look like an analysis
        # failure.  Keep the UI label compact, but run the pipeline by the
        # stable project path.
        programs = [ghidra_program_path(info, selected)] if selected else [
            ghidra_program_path(info, p if isinstance(p, str) else str(p.get('path') or p.get('name') or ''))
            for p in info.get('programs', [])
        ]
        programs = _without_backup_siblings(list(dict.fromkeys(p for p in programs if p)))
        # Older receipts keyed checkpoints by Ghidra's display leaf while new
        # receipts use the folder-qualified program path.  Merge the leaf
        # record into the canonical key before stage accounting so a resume
        # neither forgets facts nor reports two separate copies of one
        # program.  Canonical fields win because they describe the current
        # project object; older fields fill only missing provenance.
        for program in programs:
            leaf = Path(program).name
            if leaf == program or leaf not in row['checkpoints']:
                continue
            with _guard(authority):
                legacy = row['checkpoints'].pop(leaf)
            current = row['checkpoints'].get(program)
            if isinstance(legacy, dict):
                with _guard(authority):
                    row['checkpoints'][program] = {
                        **legacy,
                        **(current if isinstance(current, dict) else {}),
                    }
        execution_routes = _execution_program_bindings(locator, info, programs, root=authority.root, db=authority.db)
        execution_locator = locator
        execution_programs = {program: execution_routes[program][1] for program in programs}
        execution_locators = {program: execution_routes[program][0] for program in programs}
        with _guard(authority):
            _supersede_obsolete_probe_routes(row, execution_routes)
        with _guard(authority):
            row['executionLocator'] = execution_locator
            row['executionProgramPaths'] = execution_programs
            row['executionRoutes'] = {program: {'locator': execution_locators[program], 'program': execution_programs[program]} for program in programs}
        if len(programs) > 256:
            raise ValueError('Select at most 256 programs per preparation run.')
        with _guard(authority):
            row['programs'] = programs
        shared_probe: dict[str, Any] | None = None
        shared_probe_program = ''
        shared_route = next(
            (
                (program, execution_locators[program], execution_programs[program])
                for program in programs
                if str(execution_locators[program]).startswith('ghidra://')
                and execution_programs[program]
            ),
            None,
        )
        if shared_route:
            shared_probe_program, shared_locator, shared_program = shared_route
            update('inspect', 'running', f'Opening shared Ghidra project through {shared_program}.', completed=0, total=1)
            shared_probe = action('inspect', 'mcp.execute-script', {
                'programPath': shared_program, '_preparationProbe': True,
                'workflowWaitSeconds': 900, 'code': _ANALYSIS_PROBE,
            }, {**row, 'locator': shared_locator, 'program': shared_program})
            payload = shared_probe.get('data') or {}
            probe_ok = (
                shared_probe.get('ok')
                and isinstance(payload, dict)
                and _same_program_path(payload.get('programPath'), shared_program)
            )
            with _guard(authority):
                row['sharedSessionProbe'] = {
                    'locator': shared_locator, 'program': shared_program, 'at': time.time(),
                    'ok': bool(probe_ok), 'jobId': shared_probe.get('jobId'),
                    'observedProgramPath': payload.get('programPath') if isinstance(payload, dict) else '',
                    'error': '' if probe_ok else str(shared_probe.get('error') or shared_probe.get('log') or 'Shared program activation did not return the requested path.'),
                }
            if not probe_ok:
                detail = row['sharedSessionProbe']['error']
                update('inspect', 'partial', f'Shared Ghidra session could not open {shared_program}: {detail}', completed=0, total=1)
                raise ValueError(detail)
            update('inspect', 'completed', f'Opened shared Ghidra project through {shared_program}; {len(programs)} programs available.', completed=len(programs), total=len(programs))
        else:
            update('inspect', 'completed', f'{len(programs)} programs available.', completed=len(programs), total=len(programs))

        protection_blocked = set()
        from .protection import inspect_protection, prepare_protected_binary
        if not programs:
            update('protection', 'completed', 'No programs to prepare.', completed=0, total=0)
            update('analysis', 'blocked', 'No Ghidra program is loaded. Import a binary or open its analyzed project.')
        else:
            prepared = 0
            for program in programs:
                execution_program = execution_programs[program]
                execution_project = execution_locators[program]
                context = {**row, 'locator': execution_project, 'program': execution_program}
                with _guard(authority):
                    checkpoint = row['checkpoints'].setdefault(program, {})
                # A protection refresh must not discard a previously accepted
                # analysis receipt.  The analysis stage decides whether a
                # changed input needs work; preserving this flag makes resume
                # reuse completed programs instead of starting them again.
                if guarded_probe(_discard_unverified_probe, checkpoint, execution_program):
                    update('protection', 'running', f'Recording fresh program evidence for {program}.')
                with _guard(authority):
                    checkpoint.setdefault('analysisConfirmed', False)
                if not execution_project or not execution_program:
                    protection_blocked.add(program)
                    update('protection', 'blocked', f'{program}: no live shared or local Ghidra project binding is available; import or link its analyzed project before preparation.')
                    continue
                update('protection', 'running', f'Checking protection for {program}.', completed=prepared, total=len(programs))
                # A resumed wave must not spend another Ghidra round-trip on a
                # program whose executable identity and protection observation
                # were already recorded.  The original bytes and the derived
                # image receipt remain in the checkpoint; only an unknown or
                # changed executable needs another read-only probe.
                recorded_protection = checkpoint.get('protection')
                if isinstance(recorded_protection, dict) and checkpoint.get('executablePath'):
                    if recorded_protection.get('handling') == 'blocked':
                        protection_blocked.add(program)
                    prepared += 1
                    update('protection', 'running', f'Reusing recorded protection inspection for {program}.', completed=prepared, total=len(programs))
                    continue
                try:
                    if program == shared_probe_program and shared_probe is not None:
                        state = shared_probe
                    else:
                        state = action('protection', 'mcp.execute-script', {
                            'programPath': execution_program, '_preparationProbe': True, 'workflowWaitSeconds': 900, 'code': _ANALYSIS_PROBE
                        }, context)
                except (_PreparationIssuanceWait, _PreparationControlWait, _PreparationAuthorityRefused):
                    raise
                except Exception as exc:
                    # A single program probe must not abort the corpus wave.
                    # Persist a named blocker and continue with independent programs;
                    # the next resume can retry after the Ghidra session recovers.
                    state = {'ok': False, 'error': f'protection probe failed: {type(exc).__name__}: {exc}'}
                payload = state.get('data') or {}
                if not state['ok'] or not isinstance(payload, dict) or 'executablePath' not in payload:
                    protection_blocked.add(program)
                    update('protection', 'blocked', f'Cannot inspect stored program bytes for {program}; protection and analysis cannot proceed.')
                    continue
                if not guarded_probe(_accept_probe, checkpoint, execution_program, payload):
                    protection_blocked.add(program)
                    update('protection', 'blocked', f'{program}: the Ghidra probe returned a different program path; no evidence was accepted.')
                    continue
                source = payload.get('executablePath') or ''
                # Ghidra keeps the imported bytes in its database.  An
                # original source location may be stale after a shared
                # project moves, which must not prevent analysis of that
                # already-imported program.  Record the lost external source
                # honestly and continue through the Ghidra-backed path.
                if not Path(source).is_file():
                    with _guard(authority):
                        checkpoint['protection'] = {
                            'status': 'unknown', 'encryption': 'unknown', 'drm': 'unknown',
                            'handling': 'stored-program', 'sourcePath': source,
                            'reason': 'Original external executable is unavailable; analysis uses the bytes stored in this Ghidra program.',
                        }
                        checkpoint['externalSourceAvailable'] = False
                    prepared += 1
                    update('protection', 'running', f'{program}: original file moved; reusing stored Ghidra bytes.', completed=prepared, total=len(programs))
                    continue
                observed = inspect_protection(source)
                if observed.get('status') != 'detected':
                    with _guard(authority):
                        checkpoint['protection'] = observed
                    prepared += 1
                    update('protection', 'running', f'{program}: no protection detected.', completed=prepared, total=len(programs))
                    continue
                prior = checkpoint.get('protection') or {}
                if prior.get('handling') == 'unpacked' and prior.get('receiptPath') and Path(prior['receiptPath']).is_file():
                    with _guard(authority):
                        checkpoint['protection'] = prior
                    protection_blocked.add(program)
                    prepared += 1
                    continue
                derived = prepare_protected_binary(source, authority.root)
                with _guard(authority):
                    checkpoint['protection'] = derived
                if derived.get('handling') == 'blocked':
                    protection_blocked.add(program)
                    reason = derived.get('reason') or derived.get('blocker') or 'protection-unavailable'
                    update('protection', 'blocked', f'{program}: {reason}')
                    continue
                protection_blocked.add(program)
                prepared += 1
                update('protection', 'running', f'{program}: prepared analysis image.', completed=prepared, total=len(programs))
            if prepared == len(programs):
                update('protection', 'completed', f'{prepared} of {len(programs)} programs have an analysis image.', completed=prepared, total=len(programs))
            elif prepared:
                update('protection', 'partial', f'{prepared} of {len(programs)} programs have an analysis image.', completed=prepared, total=len(programs))
            else:
                update('protection', 'blocked', next((item.get('reason') or 'protection-unavailable' for item in row['stages'] if item['key'] == 'protection' and item.get('reason')), 'protection-unavailable'), completed=0, total=len(programs))

            analyzed = 0
            for program in programs:
                if program in protection_blocked:
                    continue
                execution_program = execution_programs[program]
                execution_project = execution_locators[program]
                context = {**row, 'locator': execution_project, 'program': execution_program}
                with _guard(authority):
                    checkpoint = row['checkpoints'].setdefault(program, {})
                update('analysis', 'running', f'Checking existing analysis for {program}.', completed=analyzed, total=len(programs))
                if checkpoint.get('analysisConfirmed') and checkpoint.get('needsAnalysis') is False:
                    analyzed += 1
                    update('analysis', 'running', f'Reusing completed analysis for {program}.', completed=analyzed, total=len(programs))
                    continue
                if 'needsAnalysis' not in checkpoint:
                    state = action('analysis', 'mcp.execute-script', {
                    'programPath': execution_program, '_preparationProbe': True, 'workflowWaitSeconds': 900, 'code': _ANALYSIS_PROBE
                    }, context)
                    payload = state.get('data') or {}
                    if not state['ok'] or not isinstance(payload, dict) or 'needsAnalysis' not in payload:
                        update('analysis', 'blocked', f'Cannot determine existing analysis for {program}; analysis was not rerun.')
                        continue
                    if not guarded_probe(_accept_probe, checkpoint, execution_program, payload):
                        update('analysis', 'blocked', f'{program}: the Ghidra probe returned a different program path; analysis was not accepted.')
                        continue
                if checkpoint.get('needsAnalysis') is False:
                    with _guard(authority):
                        checkpoint['analysisConfirmed'] = True
                    analyzed += 1
                    update('analysis', 'running', f'Reusing completed analysis for {program}.', completed=analyzed, total=len(programs))
                    continue
                # Analysis inherits the workflow's unlimited default.  Its
                # durable heartbeat, owner lease, and explicit Pause/Stop
                # controls make active work observable and controllable
                # without inventing a wall-clock expiry for a large binary.
                result = action('analysis', 'mcp.analyze-program', {
                    'programPath': execution_program,
                }, context)
                result_text = str(result.get('error') or result.get('log') or '').lower()
                # The Ghidra action deliberately refuses forced re-analysis
                # once its analyzed flag is set.  That response is an
                # authoritative completion observation, not a failed stage.
                already_analyzed = (result.get('data') or {}).get('alreadyAnalyzed') or 'already been analyzed' in result_text
                if result['ok'] or already_analyzed:
                    with _guard(authority):
                        checkpoint.update(analysisConfirmed=True, analysisCheckedAt=time.time(), needsAnalysis=False)
                    analyzed += 1
                else:
                    update('analysis', 'blocked', result.get('error') or result.get('log') or f'Analysis failed for {program}.')
            if analyzed == len(programs):
                update('analysis', 'completed', f'{analyzed} of {len(programs)} programs have analysis available.', completed=analyzed, total=len(programs))
            else:
                update('analysis', 'partial', f'{analyzed} of {len(programs)} programs have analysis available.', completed=analyzed, total=len(programs))

        # Use the canonical extractor and persistence functions in the live JVM.
        # A nonempty inventory is never replaced by automatic preparation.
        # Existing SQLite inventories are durable evidence.  Do not require a
        # second live Ghidra extraction merely because this coordinator was
        # resumed: doing so can duplicate expensive work and falsely make the
        # facts stage look empty while the corpus already contains functions.
        inventory_rows, inventory_error = query_db(
            'SELECT b.id,b.slug,b.repo_path,b.func_count,b.recovery_family,p.locator,p.program FROM binary b '
            'LEFT JOIN program_binding p ON p.source_path=b.repo_path '
            'WHERE EXISTS (SELECT 1 FROM func WHERE func.binary_id=b.id)',
            db=authority.db,
        )
        inventory_rows = inventory_rows if not inventory_error else []
        inventory_by_binding = {
            (str(item[5] or '').replace('\\', '/').rstrip('/'), str(item[6] or '').replace('\\', '/').lstrip('/')): item
            for item in inventory_rows if item[5] and item[6]
        }
        inventory_by_source = {
            str(Path(str(item[2] or '')).expanduser().resolve(strict=False)): item
            for item in inventory_rows if item[2]
        }
        extracted = 0
        analyzed_programs = [
            program for program in programs
            if program not in protection_blocked and row['checkpoints'].get(program, {}).get('analysisConfirmed')
        ]
        for program in programs:
            if program in protection_blocked or not row['checkpoints'].get(program, {}).get('analysisConfirmed'):
                continue
            with _guard(authority):
                checkpoint = row['checkpoints'].setdefault(program, {})
            binding_key = (locator.replace('\\', '/').rstrip('/'), program.replace('\\', '/').lstrip('/'))
            canonical_source = str((Path(locator).expanduser() / program.lstrip('/')).resolve(strict=False))
            existing = inventory_by_binding.get(binding_key) or inventory_by_source.get(canonical_source)
            if existing:
                with _guard(authority):
                    checkpoint.update(
                        factsComplete=True, binaryId=existing[0], slug=existing[1],
                        repoPath=existing[2], workSize=existing[3], factsReused=True,
                        recoveryFamily=_effective_recovery_family(existing[4], existing[5], existing[6], existing[0]),
                    )
                extracted += 1
                update('facts', 'running', f"{program}: reusing {existing[3]} stored functions.", completed=extracted, total=len(analyzed_programs))
                continue
            facts_path = authority.directory / f"{run_id}-{hashlib.sha256(program.encode()).hexdigest()[:12]}.facts"
            with _guard(authority):
                checkpoint.pop('programFingerprint', None)
            config = {'db': str(authority.db), 'locator': locator, 'program': program,
                      'slug': row['slug'] if len(programs) == 1 else '', 'factsPath': str(facts_path)}
            code = _inventory_script(config)
            result = action('facts', 'mcp.execute-script', {'programPath': execution_programs[program], 'code': code, 'timeout': 600}, {**row, 'locator': execution_locators[program], 'program': execution_programs[program]})
            payload = result.get('data') or {}
            if result['ok'] and isinstance(payload, dict) and payload.get('inventoryAvailable'):
                with _guard(authority):
                    checkpoint.update(factsComplete=True, factsPath=str(facts_path), binaryId=payload['binaryId'], slug=payload['slug'], repoPath=payload['repoPath'], recoveryFamily=_effective_recovery_family(payload.get('recoveryFamily'), locator, program, payload['binaryId']), programFingerprint=payload.get('programFingerprint'), arch=payload.get('arch'), workSize=payload.get('count'))
                extracted += 1
                update('facts', 'running', f"{program}: {payload['count']} stored functions available.", completed=extracted, total=len(programs))
            else:
                update('facts', 'partial', result.get('error') or result.get('log') or f'{program}: feature extraction failed; existing corpus observations preserved.', completed=extracted, total=len(programs))
        update(
            'facts',
            'completed' if analyzed_programs and extracted == len(analyzed_programs) else 'partial',
            f'{extracted} of {len(analyzed_programs)} analyzed programs have stored feature inventories.'
            if analyzed_programs else 'No analyzed programs have stored feature inventories.',
            completed=extracted, total=len(analyzed_programs),
        )
        records, error = query_db(
            'SELECT b.id,b.slug,b.repo_path,b.recovery_family,b.func_count,b.arch,b.bits,p.locator,p.program '
            'FROM binary b LEFT JOIN program_binding p ON p.source_path=b.repo_path AND rtrim(p.locator,\'/\')=? '
            'WHERE EXISTS (SELECT 1 FROM func WHERE func.binary_id=b.id)',
            (locator.rstrip('/'),),
            db=authority.db,
        )
        if error:
            legacy_records, legacy_error = query_db(
                'SELECT id,slug,repo_path,recovery_family,func_count,arch,bits FROM binary '
                'WHERE EXISTS (SELECT 1 FROM func WHERE func.binary_id=binary.id)',
                db=authority.db,
            )
            records = [(*item, None, None) for item in legacy_records]
            error = legacy_error
        records = records if not error else []
        # A resumed project must reuse its persisted function inventory.  The
        # older gate considered only facts written during this particular
        # coordinator invocation, so a restart hid valid corpus evidence and
        # incorrectly reported that there was nothing to cross-match.
        existing_by_source = {str(item[2] or ''): item for item in records}
        prepared_ids = {
            checkpoint.get('binaryId')
            for program, checkpoint in row['checkpoints'].items()
            if program in programs and checkpoint.get('analysisConfirmed') and checkpoint.get('factsComplete')
        }
        prepared_sources = {
            program for program, checkpoint in row['checkpoints'].items()
            if program in programs and checkpoint.get('analysisConfirmed')
            and (checkpoint.get('factsComplete') or program in existing_by_source)
        }
        candidates = [
            item for item in records
            if item[0] in prepared_ids or str(item[2] or '') in prepared_sources
        ]

        # A workspace-wide BSim database makes cross-build comparison possible.
        # Signature XML and receipts remain isolated by program and fingerprint.
        if programs and locator:
            committed = 0
            for program in programs:
                if program in protection_blocked:
                    continue
                if stopped():
                    raise InterruptedError('Preparation stopped before signature generation.')
                with _guard(authority):
                    checkpoint = row['checkpoints'].setdefault(program, {})
                configured = os.environ.get('AGENT_DECOMPILE_BSIM_URL', '').strip()
                fingerprint = checkpoint.get('programFingerprint') or ''
                identity = hashlib.sha256(json.dumps([locator, program, fingerprint]).encode()).hexdigest()[:24]
                bsim_file = authority.root / 'bsim' / 'corpus' / 'signatures'
                bsim_file.parent.mkdir(parents=True, exist_ok=True)
                bsim_url = configured or f'file:{bsim_file}'
                program_dir = bsim_file.parent / 'programs' / identity
                program_dir.mkdir(parents=True, exist_ok=True)
                receipt = program_dir / 'ingest.json'
                while not _BSIM_LOCK.acquire(timeout=.25):
                    if stopped():
                        raise InterruptedError('Preparation stopped while waiting for similarity indexing.')
                try:
                    database_receipt = bsim_file.parent / 'created.json'
                    database_exists = bsim_file.exists() or Path(str(bsim_file) + '.mv.db').exists()
                    ready = bool(configured) or (database_receipt.exists() and database_exists)
                    if ready and fingerprint and receipt.exists():
                        try:
                            prior = json.loads(receipt.read_text())
                        except (OSError, ValueError):
                            prior = {}
                        if prior.get('status') == 'committed' and prior.get('url') == bsim_url and prior.get('programFingerprint') == fingerprint:
                            with _guard(authority):
                                checkpoint.update(bsimComplete=True, bsimUrl=bsim_url, bsimReceipt=str(receipt), bsimFingerprint=fingerprint)
                            committed += 1
                            update('bsim', 'running', f'{program}: reusing indexed signatures for this fingerprint.', completed=committed, total=len(programs))
                            continue
                    if not ready:
                        created = action('bsim', 'corpus.bsim-createdatabase', {'bsim-url': bsim_url}, row)
                        ready = created['ok']
                        if ready:
                            database_receipt.write_text(json.dumps({'url': bsim_url, 'at': time.time()}))
                        else:
                            update('bsim', 'partial', created.get('error') or created.get('log') or 'Could not create the similarity database.')
                    if ready:
                        signature_dir = program_dir / 'xml'
                        generated = action('bsim', 'mcp.execute-script', {'programPath': execution_programs[program], 'code': _signature_script({'url': bsim_url, 'directory': str(signature_dir), 'locator': execution_locators[program], 'template': '' if configured else 'medium_nosize'}), 'timeout': 1200}, {**row, 'locator': execution_locators[program], 'program': execution_programs[program]})
                        if generated['ok'] and (generated.get('data') or {}).get('signatureCount', 0) > 0:
                            result = action('bsim', 'workbench.commit-signatures', {'bsimUrl': bsim_url, 'signatureDirectory': str(signature_dir)}, row)
                        else:
                            result = {**generated, 'ok': False, 'error': generated.get('error') or generated.get('log') or 'No signatures were generated.'}
                        if result['ok']:
                            receipt.write_text(json.dumps({'program': program, 'status': 'committed', 'url': bsim_url, 'at': time.time(), 'programFingerprint': (generated.get('data') or {}).get('programFingerprint'), 'generation': generated.get('data')}))
                        if result['ok']:
                            with _guard(authority):
                                checkpoint.update(bsimComplete=True, bsimUrl=bsim_url, bsimReceipt=str(receipt), bsimFingerprint=(generated.get('data') or {}).get('programFingerprint'))
                            committed += 1
                        update('bsim', 'running', f'{program}: signatures indexed.' if result['ok'] else f'{program}: {result.get("error") or result.get("log") or "signature generation failed"}', completed=committed, total=len(programs))
                finally:
                    _BSIM_LOCK.release()
            update('bsim', 'completed' if committed == len(programs) else 'partial', completed=committed, total=len(programs))
        else:
            update('bsim', 'blocked', 'Open the program project to generate similarity signatures.')

        from agentdecompile_recovery.corpus.corpus_config import load_match_pairs
        pairs = load_match_pairs()
        source_paths = {item[2] for item in candidates}
        pairs = [pair for pair in pairs if pair[0] in source_paths or pair[1] in source_paths]
        effective_family_by_id = {
            item[0]: _effective_recovery_family(item[3], item[7], item[8], item[0])
            for item in records
        }
        family_by_path = {str(item[2] or ''): effective_family_by_id[item[0]] for item in records}
        excluded_pairs = []
        compatible_pairs = []
        for src, dst, note in pairs:
            src_family, dst_family = family_by_path.get(src), family_by_path.get(dst)
            if src_family and dst_family and src_family == dst_family:
                compatible_pairs.append((src, dst, note))
            else:
                excluded_pairs.append({
                    'source': src, 'target': dst,
                    'reason': 'Explicit recovery-family catalog assignments differ or are unavailable.',
                    'sourceFamily': src_family, 'targetFamily': dst_family,
                })
        pairs = compatible_pairs
        # Project membership selects the sources; stored corpus evidence supplies
        # comparison candidates even when the project has only one binary.
        # Automatically schedule a *spanning forest*, never a dense graph:
        # recovery knowledge travels through logical identities, so one
        # evidence-backed edge per variant is enough to propagate it.  This
        # keeps a 16-build KotOR corpus to 15 planned comparisons instead of
        # 240 directed attempts, while explicit configured pairs above retain
        # deliberate corroboration edges.
        project_candidates = [item for item in candidates if item[4]]
        by_id = {item[0]: item for item in records}
        families: dict[str, list[dict[str, Any]]] = {}
        for item in project_candidates:
            family = effective_family_by_id[item[0]]
            families.setdefault(family, []).append({
                'id': item[0], 'repo_path': item[2], 'func_count': item[4],
                'arch': item[5], 'bits': item[6],
            })
        for family, members in sorted(families.items()):
            # Same-architecture links are the cheap, high-confidence first
            # lane.  Connect their donor hubs across architectures afterwards
            # so the full declared family remains one navigable identity graph.
            scheduled = list(spanning_forest_pairs(members))
            groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
            for member in members:
                groups.setdefault((str(member.get('arch') or ''), int(member.get('bits') or 0)), []).append(member)
            hubs = [max(group, key=lambda row: (int(row.get('func_count') or 0), str(row['id']))) for group in groups.values()]
            if hubs:
                anchor = max(hubs, key=lambda row: (int(row.get('func_count') or 0), str(row['id'])))
                scheduled.extend((anchor['id'], hub['id']) for hub in hubs if hub['id'] != anchor['id'])
            for src_id, dst_id in dict.fromkeys(scheduled):
                src = by_id.get(src_id)
                dst = by_id.get(dst_id)
                if src and dst:
                    pairs.append((src[2], dst[2], f'{family} variant spanning-forest edge; relationship unproven until comparison'))
        unique_pairs = {}
        for src, dst, note in pairs:
            if src != dst:
                key = (src, dst)
                unique_pairs.setdefault(key, (src, dst, note))
        pairs = list(unique_pairs.values())
        with _guard(authority):
            row['comparisonTargets'] = [{'source': src, 'target': dst, 'reason': note} for src, dst, note in pairs]
        with _guard(authority):
            row['comparisonTargetsFrozenAt'] = time.time()
        def input_progress(completed: int, total: int, source: str = '', functions_read: int = 0) -> None:
            if stopped():
                raise InterruptedError('Workflow stopped while reading comparison inputs.')
            progress = _matching_inventory_progress_kwargs(
                pair_count=len(pairs),
                inventory_completed=completed,
                inventory_total=total,
                current_program=programs[0] if len(programs) == 1 else '',
                source=source,
                functions_read=functions_read,
            )
            detail = progress.pop('_reason_detail')
            update('matching', 'running', f'Reading comparison evidence: {completed} of {total} inventories.{detail}',
                   **progress)
        comparison_inputs.update(_matching_input_digests({path for src, dst, _ in pairs for path in (src, dst)}, input_progress, db=authority.db))
        # A configured pair can point at a slice or an old project member
        # whose binary row has no function inventory.  Passing that pair to
        # the matcher spends a worker constructing an empty side and cannot
        # produce an identity binding.  Retain the excluded target and reason
        # for the operator, but admit only evidence-backed inventories.
        admitted_pairs = []
        for pair in pairs:
            src, dst, note = pair
            missing = [
                path for path in (src, dst)
                if not isinstance(comparison_inputs.get(path), dict)
                or comparison_inputs[path].get('state') == 'missing'
                or int(comparison_inputs[path].get('functionCount') or 0) <= 0
            ]
            if missing:
                excluded_pairs.append({'source': src, 'target': dst, 'reason': 'No stored function inventory for ' + ', '.join(missing), 'recoveryFamily': family_by_path.get(src)})
            else:
                admitted_pairs.append(pair)
        pairs = admitted_pairs
        with _guard(authority):
            row['comparisonTargets'] = [{'source': src, 'target': dst, 'reason': note, 'recoveryFamily': family_by_path.get(src)} for src, dst, note in pairs]
        with _guard(authority):
            row['excludedComparisonTargets'] = excluded_pairs
        with _guard(authority):
            row['comparisonTargetsFrozenAt'] = time.time()
        with _guard(authority):
            row['comparisonInputs'] = copy.deepcopy(comparison_inputs)
        update('matching', 'running', 'Comparison targets and input evidence frozen.', completed=0, total=len(pairs), progressUnit='comparisons', workProgress=None)
        _write(row, authority=authority)
        if not pairs:
            update('matching', 'blocked', 'No other binary has stored function features to compare. Import or analyze a comparison binary.')
        else:
            matched = 0
            admitted = 0
            deferred = 0
            to_run = []
            for src, dst, note in pairs:
                existing = read_comparison_receipt(run_id, src, dst, comparison_inputs, authority=authority)
                if existing:
                    matched += 1
                    update('matching', 'running', f'Reusing completed comparison receipt: {Path(src).name} → {Path(dst).name}.', completed=matched, total=len(pairs))
                    continue
                to_run.append((src, dst, note))
            admitted = len(to_run)
            # Each corpus.match-pair call is a standalone subprocess reading
            # sqlite-persisted facts; it never opens the shared PyGhidra
            # project, so these comparisons are independent and safe to run
            # concurrently up to _matching_concurrency() workers.
            progress_lock = threading.Lock()

            def _run_pair(item: tuple[str, str, str]) -> tuple[str, str, dict[str, Any]]:
                src, dst, note = item
                result = action('matching', 'corpus.match-pair', {'db': str(authority.db), 'src': src, 'dst': dst, 'run': f'prepare-{run_id}', 'note': note}, row)
                return src, dst, result

            if to_run:
                workers = min(_matching_concurrency(), len(to_run))
                pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f'match-{run_id[:8]}')
                interrupted = False
                try:
                    futures = [pool.submit(_run_pair, item) for item in to_run]
                    try:
                        for future in as_completed(futures):
                            src, dst, result = future.result()
                            with progress_lock:
                                if result['ok']:
                                    record_comparison_receipt(run_id, src, dst, result, comparison_inputs, authority=authority)
                                    matched += 1
                                elif result.get('paused'):
                                    continue
                                update('matching', 'running', result.get('error') or f'{Path(src).name} → {Path(dst).name}: {"compared" if result["ok"] else "failed"}.', completed=matched, total=len(pairs))
                    except InterruptedError:
                        interrupted = True
                        for pending in futures:
                            pending.cancel()
                        raise
                finally:
                    pool.shutdown(wait=not interrupted, cancel_futures=interrupted)
            if _read_control(run_id, root=authority.root, strict=True).get('operation') == 'pause':
                update('matching', 'paused', f'Paused after {matched} of {len(pairs)} durable comparison receipts.', completed=matched, total=len(pairs), deferred=len(pairs) - matched)
                raise _PauseRequested()
            update('matching', 'completed' if matched == len(pairs) else 'partial', f'{matched} of {len(pairs)} pairs compared. {deferred} comparisons await admission.' if deferred else f'{matched} of {len(pairs)} pairs compared.', completed=matched, total=len(pairs), deferred=deferred)
        if pairs and matched:
            merged = action('matching', 'workbench.merge-evidence', {'db': str(authority.db), 'run': f'prepare-{run_id}'}, row)
            update('matching', 'completed' if merged['ok'] and matched == len(pairs) else 'partial', 'Compared identities bound; existing human metadata retained.' if merged['ok'] else merged.get('error') or 'Knowledge binding could not finish.', completed=matched, total=len(pairs))
        from .workflow import continue_recovery
        recovery_families: dict[str, list[str]] = {}
        for program in programs:
            checkpoint = row['checkpoints'].get(program, {})
            family = str(checkpoint.get('recoveryFamily') or f"unclassified:{checkpoint.get('binaryId') or hashlib.sha256(program.encode()).hexdigest()[:12]}")
            with _guard(authority):
                checkpoint['recoveryFamily'] = family
            recovery_families.setdefault(family, []).append(program)
        with _guard(authority):
            family_receipts = row.setdefault('recoveryFamilies', {})
        for family, members in sorted(recovery_families.items()):
            eligible = [program for program in members if row['checkpoints'].get(program, {}).get('analysisConfirmed') and row['checkpoints'].get(program, {}).get('factsComplete')]
            with _guard(authority):
                family_receipts[family] = {
                    'family': family, 'programs': members, 'eligiblePrograms': eligible,
                    'state': 'running' if eligible else 'waiting', 'updatedAt': time.time(),
                }
            if eligible:
                continue_recovery(
                    _snapshot(authority), authority.root, authority.db, action, update,
                    mutate_state=_workflow_mutator(authority),
                    execution_routes=execution_routes, recovery_family=family,
                    programs=eligible, all_programs=programs,
                )
            else:
                with _guard(authority):
                    family_receipts[family]['reason'] = 'Waiting for this family\'s analysis and facts receipts.'
        _write(row, authority=authority)
        routed = sum(bool(execution_locators[program] and execution_programs[program]) for program in programs)
        probed = sum(
            _same_program_path(row['checkpoints'].get(program, {}).get('observedProgramPath'), execution_programs[program])
            for program in programs
        )
        with _guard(authority):
            row['executionSummary'] = {'programs': len(programs), 'routed': routed, 'probed': probed}
        if programs and (not routed or not probed):
            with _guard(authority):
                row.update(
                    status='blocked',
                    error=(
                        'No executable Ghidra project route was found for this preparation.'
                        if not routed else
                        'No program probe receipt matched its requested Ghidra program; no execution evidence was accepted.'
                    ),
                )
        else:
            with _guard(authority):
                row['status'] = 'completed' if all(stage['status'] == 'completed' for stage in row['stages']) else 'partial'
    except _PreparationIssuanceWait as exc:
        issuance_wait = True
        return 1, json.dumps(authority_refusal(exc)[0])
    except _PreparationControlWait as exc:
        issuance_wait = True
        _diagnostic(authority.root, run_id, exc)
        return 1, json.dumps(authority_refusal(exc)[0])
    except _PreparationAuthorityRefused as exc:
        _poison(authority, exc)
        return 1, json.dumps(authority_refusal(exc)[0])
    except _PauseRequested:
        with _guard(authority):
            row.update(status='paused', error='')
    except InterruptedError as exc:
        with _guard(authority):
            row.update(status='cancelled' if cancel.is_set() else 'budget-stop', error=str(exc))
    except Exception as exc:
        with _guard(authority):
            row.update(status='blocked', error=str(exc))
    finally:
        try:
            if authority.state == 'current' and not issuance_wait:
                with _guard(authority):
                    provider_block = next((stage for stage in row['stages'] if str(stage.get('nextAction', '')).startswith('provider_')), None)
                    if provider_block is not None:
                        row.update(status='blocked', error=provider_block.get('reason', 'MCP dispatch budget blocked this preparation.'))
                    for stage in row['stages']:
                        if stage['status'] in {'running', 'queued', 'waiting', 'cancelling'}:
                            stage.update(status='blocked', reason=row.get('error') or 'A prerequisite prevented this stage from running.')
                    _write(row, authority=authority)
        finally:
            _retire_capacity(authority.slot)
            _release_lease(run_id, expectedAuthority=authority)
    return (0 if row['status'] in {'completed', 'partial', 'paused'} else 1), json.dumps({**row, 'providerBudget': mcp_budget.public(row)}, indent=2)


class _PauseRequested(Exception):
    """Internal control-flow marker for a durable coordinator pause."""


def _inventory_script(config: dict[str, Any]) -> str:
    """Generate orchestration only; feature extraction remains in corpus.extract."""
    return "import json\nconfig = json.loads(" + repr(json.dumps(config)) + ")\n" + r"""
from pathlib import Path
import time
from agentdecompile_recovery.corpus.store import connect
from agentdecompile_recovery.corpus.extract import functions_from_program, upsert_binary, persist_functions, slugify
from ghidra.util.task import TimeoutTaskMonitor
from java.util.concurrent import TimeUnit
monitor = TimeoutTaskMonitor.timeoutIn(600, TimeUnit.SECONDS)
con = connect(config['db'])
try:
    selected = con.execute('SELECT id,slug,repo_path FROM binary WHERE slug=?', (config['slug'],)).fetchone() if config['slug'] else None
    if selected is not None and str(selected[2]).rstrip('/') == config['locator'].rstrip('/'):
        # A project tab's slug identifies the container, not its first program.
        selected = None
    repo = config['locator'].rstrip('/') + '/' + config['program'].lstrip('/')
    if selected is None:
        selected = con.execute('SELECT id,slug,repo_path FROM binary WHERE repo_path=?', (repo,)).fetchone()
    if selected is None:
        executable = str(currentProgram.getExecutablePath())
        selected = con.execute('SELECT id,slug,repo_path FROM binary WHERE repo_path=?', (executable,)).fetchone()
    if selected is None:
        fingerprint = str(currentProgram.getExecutableMD5())
        columns = {column[1] for column in con.execute('PRAGMA table_info(binary)')}
        if 'md5' in columns and len(fingerprint) == 32 and all(c in '0123456789abcdefABCDEF' for c in fingerprint):
            matching = con.execute('SELECT id,slug,repo_path FROM binary WHERE lower(md5)=lower(?)', (fingerprint,)).fetchall()
            if len(matching) == 1:
                selected = matching[0]
            elif len(matching) > 1:
                raise ValueError('More than one registered build has this executable fingerprint. Select its registered binary before preparing.')
    if selected is None:
        binary_id = upsert_binary(con, repo_path=repo, slug=slugify(repo), program=currentProgram)
        selected = con.execute('SELECT id,slug,repo_path FROM binary WHERE id=?', (binary_id,)).fetchone()
    binary_id, slug, repo = tuple(selected)
    previous_md5 = con.execute('SELECT md5 FROM binary WHERE id=?', (binary_id,)).fetchone()[0]
    current_md5 = str(currentProgram.getExecutableMD5())
    if previous_md5 and current_md5 and str(previous_md5).lower() != current_md5.lower():
        raise ValueError('Selected corpus build has a different executable fingerprint. Select the matching build before indexing.')
    # Registration precedes analysis. Refresh measured program metadata even
    # when the roster row already exists, retaining operator classification.
    classification = con.execute('SELECT game,platform,variant,role,recovery_family FROM binary WHERE id=?', (binary_id,)).fetchone()
    upsert_binary(con, repo_path=repo, slug=slug, program=currentProgram,
                  meta=dict(zip(('game', 'platform', 'variant', 'role', 'recovery_family'), classification)))
    con.execute('CREATE TABLE IF NOT EXISTS program_binding (source_path TEXT NOT NULL, locator TEXT NOT NULL, program TEXT NOT NULL, updated REAL NOT NULL, PRIMARY KEY(source_path,locator))')
    con.execute('INSERT INTO program_binding VALUES(?,?,?,?) ON CONFLICT(source_path,locator) DO UPDATE SET program=excluded.program,updated=excluded.updated', (repo, config['locator'], config['program'], time.time()))
    con.commit()
    count = con.execute('SELECT COUNT(*) FROM func WHERE binary_id=?', (binary_id,)).fetchone()[0]
    reused = bool(count)
    if not count:
        functions = functions_from_program(currentProgram, monitor)
        monitor.checkCancelled()
        con.execute('BEGIN IMMEDIATE')
        # Another worker may have populated or curated this build during extraction.
        count = con.execute('SELECT COUNT(*) FROM func WHERE binary_id=?', (binary_id,)).fetchone()[0]
        if not count:
            count = persist_functions(con, binary_id, functions)
        else:
            reused = True
            con.rollback()
    recovery_family = con.execute('SELECT recovery_family FROM binary WHERE id=?', (binary_id,)).fetchone()[0]
    receipt = {'binaryId': binary_id, 'slug': slug, 'repoPath': repo, 'recoveryFamily': recovery_family, 'count': count,
               'inventoryAvailable': count > 0, 'reused': reused, 'claim': 'advisory',
               'tool': 'corpus.extract.functions_from_program', 'program': config['program'],
               'programFingerprint': str(currentProgram.getExecutableMD5()), 'arch': str(currentProgram.getLanguageID())}
    target = Path(config['factsPath'])
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(receipt), encoding='utf-8')
    temporary.replace(target)
    __result__ = json.dumps(receipt)
finally:
    con.close()
"""


def _signature_script(config: dict[str, Any]) -> str:
    """Mirror Ghidra BulkSignatures on the already-owned currentProgram."""
    return "import json\nconfig = json.loads(" + repr(json.dumps(config)) + ")\n" + r"""
from pathlib import Path
from java.net import URL
from java.io import FileWriter
from ghidra.features.bsim.query import BSimClientFactory, FunctionDatabase, GenSignatures
from ghidra.util.task import TimeoutTaskMonitor
from java.util.concurrent import TimeUnit
monitor = TimeoutTaskMonitor.timeoutIn(1200, TimeUnit.SECONDS)
client = None
generator = None
try:
    if config.get('template'):
        configuration = FunctionDatabase.loadConfigurationTemplate(config['template'])
        info = configuration.info
        vectors = FunctionDatabase.generateLSHVectorFactory()
        vectors.set(configuration.weightfactory, configuration.idflookup, info.settings)
    else:
        client = BSimClientFactory.buildClient(URL(config['url']), False)
        if not client.initialize():
            raise RuntimeError(str(client.getLastError().message))
        info = client.getInfo()
        vectors = client.getLSHVectorFactory()
    generator = GenSignatures(True)
    generator.setVectorFactory(vectors)
    generator.addExecutableCategories(info.execats)
    generator.addFunctionTags(info.functionTags)
    generator.addDateColumnName(info.dateColumnName)
    repository = config['locator']
    if not repository.startswith('ghidra:'):
        project_path = Path(repository)
        if project_path.suffix.lower() == '.gpr':
            project_path = project_path.with_suffix('')
        repository = 'ghidra:' + str(project_path)
    generator.openProgram(currentProgram, None, None, None, repository, GenSignatures.getPathFromDomainFile(currentProgram))
    functions = currentProgram.getFunctionManager()
    generator.scanFunctions(functions.getFunctions(True), functions.getFunctionCount(), monitor)
    descriptions = generator.getDescriptionManager()
    count = int(descriptions.numFunctions())
    if count == 0:
        raise RuntimeError('The program produced no similarity signatures.')
    md5 = str(currentProgram.getExecutableMD5())
    if len(md5) != 32 or any(c not in '0123456789abcdefABCDEF' for c in md5):
        raise RuntimeError('A valid executable MD5 is required for BSim signature import.')
    directory = Path(config['directory'])
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / ('sigs_' + md5)
    temporary = target.with_suffix('.tmp')
    writer = FileWriter(str(temporary))
    try:
        descriptions.saveXml(writer)
    finally:
        writer.close()
    temporary.replace(target)
    __result__ = json.dumps({'signatureCount': count, 'path': str(target), 'program': str(currentProgram.getName()), 'programFingerprint': md5, 'claim': 'advisory'})
finally:
    if generator is not None:
        generator.dispose()
    if client is not None:
        client.close()
"""


def _retry_input_revision(name: str, fields: dict[str, Any]) -> list[Any]:
    from .workflow import input_revision
    # Matcher semantic inputs are the frozen source/target inventory below.
    # A shared SQLite KB's mtime/size also changes for unrelated programs.
    observed = {key: value for key, value in fields.items() if key != 'kb'} if name == 'corpus.match-pair' else fields
    return input_revision(observed)


def _matching_retry_prior(history: dict[str, Any], action_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    if action_id in history:
        return dict(history[action_id])
    siblings = [(key, value) for key, value in history.items()
                if isinstance(value, dict) and value.get('action') == 'corpus.match-pair'
                and value.get('params') == fields]
    if any('retryBasis' in value for _, value in siblings):
        # A new semantic inventory after migration is a genuinely new basis.
        return {}
    legacy = [(key, value) for key, value in siblings if value.get('status') != 'ok']
    if not legacy:
        return {}
    # Legacy hashes cannot reveal which KB revision they included. Conservatively
    # carry spending once instead of silently refunding old failures on upgrade.
    attempts = sum(value.get('attempts', 0) if isinstance(value.get('attempts', 0), int)
                   else MAX_ACTION_ATTEMPTS for _, value in legacy)
    unresolved = next((value for _, value in legacy if value.get('status') in
                       {'submitting', 'queued', 'running', 'interrupted', 'cancelling'}), None)
    previous = dict(unresolved or legacy[-1][1])
    previous.update(attempts=attempts, retryMigratedFrom=[key for key, _ in legacy])
    return previous


def _decode_job_output(text: str) -> Any:
    """Decode both ordinary and crash-reconciled receipts identically."""
    try:
        data, _ = json.JSONDecoder().raw_decode(text[text.index('{'):])
        if isinstance(data, dict) and isinstance(data.get('result'), str):
            envelope = data
            try:
                result = json.loads(data['result'])
            except ValueError:
                return data
            if isinstance(result, dict):
                executed = envelope.get('executedProgram')
                if isinstance(executed, dict) and executed.get('path'):
                    result['programPath'] = str(executed['path'])
                # Do not discard ownership warnings carried by an outer tool
                # envelope when its nested scientific payload is decoded.
                if envelope.get('ownershipResolved') is False or envelope.get('ownershipUnresolved'):
                    result['ownershipUnresolved'] = True
            data = result
        return data
    except (ValueError, TypeError):
        return None


def _unresolved_job_ownership(data: Any, previous: Any = None) -> bool:
    current = data if isinstance(data, dict) else {}
    old = previous if isinstance(previous, dict) else {}
    return bool(current.get('ownershipResolved') is False or current.get('ownershipUnresolved')
                or (old.get('ownershipUnresolved') and current.get('ownershipResolved') is not True))


def _remember_retry_decision(row: dict[str, Any], action_id: str, name: str, decision: dict[str, Any]) -> None:
    """Bounded public projection; complete decision history remains on actions."""
    decisions = row.setdefault('retryDecisions', {})
    decisions.pop(action_id, None)
    decisions[action_id] = {'action': name, **decision}
    while len(decisions) > 64:
        decisions.pop(next(iter(decisions)))


def _action_prior_for_retry(name: str, prior: dict[str, Any]) -> dict[str, Any]:
    """Observe one repaired prerequisite without discarding attempt history.

    Matching idempotence never grants fresh retries. A repaired BSim launcher
    makes a prior missing-launcher failure eligible only within its original cap.
    """
    data = (prior.get('result') or {}).get('data') or {}
    if (
        name == 'corpus.bsim-createdatabase' and prior.get('status') == 'failed'
        and data.get('returncode') == 127
        and data.get('error') == 'Ghidra support/bsim not found (set GHIDRA_INSTALL_DIR)'
    ):
        from agentdecompile_recovery.corpus.bsim_ops import find_bsim_launcher
        if find_bsim_launcher() is not None:
            return {**prior, 'retryPrerequisiteRecovered': 'bsim_launcher_available'}
    return prior


def _matching_inventory_progress_kwargs(
    *,
    pair_count: int,
    inventory_completed: int,
    inventory_total: int,
    current_program: str = '',
    source: str = '',
    functions_read: int = 0,
) -> dict[str, Any]:
    """Keep matching stage totals on pair count while inventory digest runs."""
    detail = f' {Path(source).name}: {functions_read:,} functions read.' if source else ''
    return {
        'completed': 0,
        'total': pair_count,
        'progressUnit': 'comparisons',
        'currentProgram': current_program,
        'workProgress': {
            'completed': inventory_completed,
            'total': inventory_total,
            'unit': 'binary inventories',
        },
        '_reason_detail': detail,
    }


def _comparison_path(run_id: str, src: str, dst: str, *, authority, receipt_id, generation=None) -> Path:
    if not _valid_id(run_id) or run_id != authority.run_id:
        raise ValueError('Invalid preparation ID')
    key = hashlib.sha256(json.dumps([str(authority.db), src, dst]).encode()).hexdigest()
    return authority.directory / 'comparisons' / run_id / ((generation or authority.generation) + '-' + receipt_id + '-' + key + '.json')


def _matching_input_digests(paths: set[str], progress: Any = None, *, db: Path | None = None) -> dict[str, Any]:
    """Hash matcher inputs once per binary per wave, in one SQLite snapshot."""
    from ..store import decomp_read_state

    if not paths:
        return {}
    result = {}
    if progress:
        progress(0, len(paths))
    with sqlite3.connect(f'{Path(db if db is not None else live_db()).resolve().as_uri()}?mode=ro', uri=True) as con:
        con.row_factory = sqlite3.Row
        con.execute('BEGIN')
        available = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        decomp_state = decomp_read_state(con)
        for source in sorted(paths):
            if progress:
                progress(len(result), len(paths), source, 0)
            binary = con.execute('SELECT * FROM binary WHERE repo_path=?', (source,)).fetchone()
            if binary is None:
                result[source] = {'source': source, 'state': 'missing'}
                if progress:
                    progress(len(result), len(paths))
                continue
            digest = hashlib.sha256()
            count = 0
            def add(value: Any) -> None:
                digest.update(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode())
                digest.update(b'\n')
            add({'schema': 'matcher-input-v2', 'binary': dict(binary), 'decompMode': decomp_state})
            for row in con.execute('SELECT * FROM func WHERE binary_id=? ORDER BY addr,id', (binary['id'],)):
                add({'func': dict(row)})
                count += 1
                if progress and count % 5000 == 0:
                    progress(len(result), len(paths), source, count)
            if 'calledge' in available:
                for row in con.execute('SELECT caller_addr,callee_addr FROM calledge WHERE binary_id=? ORDER BY caller_addr,callee_addr', (binary['id'],)):
                    add({'edge': list(row)})
            if decomp_state is not None:
                for row in con.execute(f'SELECT addr,n_tokens,n_lines,max_nest,n_calls,n_locals,n_deref,n_index,n_field,ctrl,ops,skeleton_hash,{decomp_state} AS selected_fingerprint FROM main.decomp WHERE binary_id=? AND ok=1 ORDER BY addr', (binary['id'],)):
                    add({'decomp': dict(row)})
            result[source] = {'source': source, 'schema': 'matcher-input-v2', 'digest': digest.hexdigest(), 'functionCount': count, 'md5': binary['md5']}
            if progress:
                progress(len(result), len(paths))
    return result


def _comparison_inventory(src: str, dst: str, inputs: dict[str, Any] | None = None) -> list[Any]:
    if inputs is not None:
        return [inputs.get(path, {'source': path, 'state': 'missing'}) for path in (src, dst)]
    rows, error = query_db(
        'SELECT b.repo_path,b.md5,COUNT(f.id) FROM binary b LEFT JOIN func f ON f.binary_id=b.id '
        'WHERE b.repo_path IN (?,?) GROUP BY b.id ORDER BY b.repo_path', (src, dst))
    if error:
        raise ValueError(error)
    return [list(row) for row in rows]


def record_comparison_receipt(run_id: str, src: str, dst: str, result: dict[str, Any], inputs: dict[str, Any] | None = None, *, authority) -> None:
    """Only a guarded committed reference can publish current reusable evidence."""
    if not result.get('ok') or not result.get('jobId') or inputs is None:
        raise ValueError('A completed comparison and detached wave inventory are required.')
    basis = copy.deepcopy(_comparison_inventory(src, dst, inputs))
    pair_key = hashlib.sha256(json.dumps([str(authority.db), src, dst]).encode()).hexdigest()
    receipt_id = uuid.uuid4().hex
    path = _comparison_path(run_id, src, dst, authority=authority, receipt_id=receipt_id)
    receipt = {'preparationId': run_id, 'db': str(authority.db), 'source': src, 'target': dst,
               'jobId': result['jobId'], 'jobStatus': 'ok', 'completedAt': result.get('finishedAt'),
               'result': copy.deepcopy(result.get('data')), 'claim': 'advisory', 'scope': 'completed-pair-comparison',
               'inventory': basis, 'generation': authority.generation, 'receiptId': receipt_id,
               'freshnessLimit': 'Inputs are frozen once per matching wave; later changes invalidate reuse.'}
    with _guard(authority):
        if authority.run_id != run_id or authority.row.get('comparisonInputs') != inputs:
            refusal = _refusal(run_id, authority=authority, reason='Comparison wave basis changed.')
            _poison(authority, refusal)
            raise refusal
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _sync_directory(path.parent.parent)
            _sync_directory(authority.directory)
            _atomic_json(path, receipt, authority.generation)
        except Exception as exc:
            refusal = _refusal(run_id, 'preparation_persistence_failed', authority=authority)
            _poison(authority, refusal)
            raise refusal from exc
        authority.row.setdefault('comparisonReceipts', {})[pair_key] = {
            'generation': authority.generation, 'receiptId': receipt_id, 'path': str(path), 'inputBasis': basis}
        _write(authority.row, authority=authority)


def read_comparison_receipt(run_id: str, src: str, dst: str, inputs: dict[str, Any] | None = None, *, authority) -> dict[str, Any] | None:
    if inputs is None:
        return None
    basis = copy.deepcopy(_comparison_inventory(src, dst, inputs))
    pair_key = hashlib.sha256(json.dumps([str(authority.db), src, dst]).encode()).hexdigest()
    with _guard(authority):
        reference = copy.deepcopy(authority.committed.get('comparisonReceipts', {}).get(pair_key))
        if not reference or reference.get('inputBasis') != basis:
            return None
        if not _valid_id(reference.get('generation')) or not _valid_id(reference.get('receiptId')):
            return None
        expected = _comparison_path(run_id, src, dst, authority=authority,
                                    receipt_id=reference['receiptId'], generation=reference['generation'])
        if reference.get('path') != str(expected):
            return None
        try:
            receipt = _load_row(expected)
        except (OSError, ValueError):
            return None
        if any(receipt.get(key) != value for key, value in {
            'jobStatus': 'ok', 'source': src, 'target': dst, 'db': str(authority.db),
            'preparationId': run_id, 'inventory': basis, 'generation': reference['generation'],
            'receiptId': reference['receiptId']}.items()):
            return None
        return receipt


def _control_path(run_id: str, *, root=None) -> Path:
    if not _valid_id(run_id):
        raise ValueError('Invalid preparation ID')
    return (root or _directory().parent) / 'preparations' / 'controls' / (run_id + '.json')


@contextmanager
def _command_lock(run_id, root):
    path = _control_path(run_id, root=root)
    key = (str(root), run_id)
    lease = None
    try:
        path.parent.mkdir(exist_ok=True)
        _sync_directory(path.parent.parent)
        lease = path.with_suffix('.lock').open('a+')
        try:
            _lock_lease(lease)
        except BlockingIOError as exc:
            raise _PreparationControlWait(run_id, root) from exc
        # Another command writer may have faulted after the caller precheck.
        if key in _COMMAND_FAULTS:
            raise _COMMAND_FAULTS[key]
        yield path
    except OSError as exc:
        refusal = _refusal(run_id, 'preparation_persistence_failed', 'control')
        _COMMAND_FAULTS[key] = refusal
        raise refusal from exc
    finally:
        if lease is not None:
            lease.close()


def _load_command(path):
    try:
        value = _load_row(path)
    except FileNotFoundError:
        return {}
    if type(value.get('commandRevision')) is not int or value['commandRevision'] < 1:
        raise ValueError('Control revision is unavailable')
    if value.get('operation') is not None and (not isinstance(value['operation'], str) or value['operation'] not in {'pause', 'resume', 'stop'}):
        raise ValueError('Unknown control operation')
    if 'priority' in value and (type(value['priority']) is not int or not 0 <= value['priority'] <= 100):
        raise ValueError('Unknown control priority')
    if value.get('deadline') is not None and (type(value['deadline']) not in {int, float} or not math.isfinite(value['deadline'])):
        raise ValueError('Unknown control deadline')
    if value.get('budgetSeconds') is not None and (type(value['budgetSeconds']) is not int or not 1 <= value['budgetSeconds'] <= MAX_BUDGET_SECONDS):
        raise ValueError('Unknown control budget')
    return value


def _read_control(run_id: str, *, root=None, strict=False) -> dict[str, Any]:
    try:
        fault = _COMMAND_FAULTS.get((str(root or _directory().parent), run_id))
        if fault is not None:
            raise fault
        if strict:
            with _command_lock(run_id, root or _directory().parent) as path:
                return _load_command(path)
        return _load_command(_control_path(run_id, root=root))
    except (_PreparationControlWait, _PreparationAuthorityRefused, OSError, ValueError, OverflowError) as exc:
        if strict:
            if isinstance(exc, (_PreparationControlWait, _PreparationAuthorityRefused)):
                raise
            refusal = _refusal(run_id, 'preparation_persistence_failed' if isinstance(exc, OSError) else 'preparation_continuity_required', 'control', reason='Control state cannot be established.')
            _COMMAND_FAULTS[(str(root or _directory().parent), run_id)] = refusal
            raise refusal from exc
        return {'unavailable': True}


def _revise_admission_budget(run_id: str, params: dict[str, Any], *, provider: bool = False) -> dict[str, Any]:
    allocation = 'maxMcpToolCalls' if provider else 'maxActionAdmissions'
    accounting = mcp_budget if provider else admission_budget
    if allocation not in params and params.get('unlimited') is not True:
        raise ValueError(f'Supply {allocation} or explicit unlimited=true')
    with _LOCK:
        if run_id in _ACTIVE or run_id in _LEASES:
            raise _refusal(run_id, phase='control', reason='Pause and drain before changing allocation; faults require continuity reconciliation.')
    authority = _acquire_authority(_directory().parent.resolve(), Path(live_db()).resolve(), run_id)
    try:
        with _guard(authority, phase='control'):
            accounting.revise(authority.row, expected_revision=params.get('expectedAllocationRevision'),
                              maximum=params.get(allocation), unlimited=params.get('unlimited', False))
            _write(authority.row, authority=authority, phase='control')
            result = copy.deepcopy(authority.row)
        return {**_public_run(result), 'controlAcknowledged': True, 'nextAction': 'resume',
                'wakeCondition': 'explicit_resume', 'reason': 'Allocation revised without changing spending.'}
    finally:
        _release_lease(run_id, expectedAuthority=authority)
        _ADMISSION_WAKE.set()


def control(params: dict[str, Any]) -> dict[str, Any]:
    run_id = str(params.get('preparation_id') or '')
    operation = str(params.get('operation') or '')
    if operation in {'admission-budget', 'provider-budget'}:
        return _revise_admission_budget(run_id, params, provider=operation == 'provider-budget')
    if operation not in {'pause', 'resume', 'stop', 'budget', 'priority'}:
        raise ValueError('Choose pause, resume, stop, budget, or priority.')
    root = _directory().parent.resolve()
    row = _read(run_id)
    if (str(root), run_id) in _COMMAND_FAULTS:
        raise _COMMAND_FAULTS[(str(root), run_id)]
    with _command_lock(run_id, root) as path:
        try:
            command = _load_command(path)
        except (ValueError, OverflowError) as exc:
            refusal = _refusal(run_id, phase='control', reason='Control state requires reconciliation.')
            _COMMAND_FAULTS[(str(root), run_id)] = refusal
            raise refusal from exc
        if operation == 'priority':
            value = params.get('priority')
            if type(value) is not int or not 0 <= value <= 100:
                raise ValueError('Priority must be an integer from 0 to 100; higher values run first.')
            command.update(priority=value, priorityReason=f'Operator priority {value}; applies to waiting admission, without interrupting active work.')
        elif operation == 'budget':
            value = None if params.get('unlimited') is True else params.get('seconds')
            if 'seconds' not in params and params.get('unlimited') is not True:
                raise ValueError('Supply seconds:null for unlimited, or 1 to 604800 seconds.')
            if value is not None and (type(value) is not int or not 1 <= value <= MAX_BUDGET_SECONDS):
                raise ValueError('Budget must be null for unlimited, or 1 to 604800 seconds.')
            command.update(deadline=time.time() + value if value is not None else None, budgetSeconds=value, budgetOrigin='explicit')
        else:
            command['operation'] = operation
        command.update(commandRevision=command.get('commandRevision', 0) + 1, updatedAt=time.time())
        try:
            _atomic_json(path, command, 'command')
        except OSError as exc:
            refusal = _refusal(run_id, 'preparation_persistence_failed', 'control')
            _COMMAND_FAULTS[(str(root), run_id)] = refusal
            raise refusal from exc
    _ADMISSION_WAKE.set()
    may_resume = operation == 'resume' or (operation == 'budget' and row['status'] == 'budget-stop' and command.get('operation') not in {'pause', 'stop'})
    if may_resume and run_id not in _ACTIVE:
        return submit({key: row.get(key, '') for key in ('locator', 'program', 'slug')}, resume=True)
    if (str(root), run_id) in _FAULTS or (str(root), run_id) in _SUSPENDED:
        raise _refusal(run_id, phase='control')
    return {**row, 'control': command, 'controlAcknowledged': True,
            'deadline': command.get('deadline', row.get('deadline')),
            'budgetSeconds': command.get('budgetSeconds', row.get('budgetSeconds')),
            'queuePriority': command.get('priority', row.get('queuePriority', 50))}


def recover_interrupted() -> list[dict[str, Any]]:
    """Historical rows are observations; only retained session witnesses resume."""
    recovered = []
    _start_admission_worker()
    root = _directory().parent.resolve()
    for row in list_runs():
        if row.get('supersededBy') or row.get('status') not in {'interrupted', 'queued', 'running'}:
            continue
        try:
            witness = _HEALTHY.get((str(root), row['id']))
            if witness is None or not witness.valid or witness.session is not _SESSION:
                raise _refusal(row['id'])
            recovered.append(submit({key: row.get(key, '') for key in ('locator', 'program', 'slug')}, resume=True, _admit=True))
        except _PreparationIssuanceWait as exc:
            recovered.append(_diagnostic(root, row['id'], exc))
        except _PreparationControlWait as exc:
            recovered.append(_diagnostic(root, row['id'], exc))
        except _PreparationAuthorityRefused as exc:
            recovered.append(_diagnostic(root, row['id'], exc))
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
            recovered.append(_diagnostic(root, row['id'], _refusal(row['id'], 'preparation_persistence_failed' if isinstance(exc, OSError) else 'preparation_continuity_required')))
    return recovered
