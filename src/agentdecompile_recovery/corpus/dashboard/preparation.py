"""Durable, missing-only project preparation shared by both frontends."""
from __future__ import annotations

import hashlib
import json
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
_ACTIVE: set[str] = set()
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
            raise BlockingIOError(str(exc)) from exc
    else:
        import fcntl
        fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _directory() -> Path:
    root = live_root()
    if root is None:
        raise ValueError('Choose a server workspace before preparing projects.')
    directory = root / 'preparations'
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _write(row: dict[str, Any]) -> None:
    row['updatedAt'] = time.time()
    path = _directory() / (row['id'] + '.json')
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(row, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    # The admission intent and spent budget must survive a crash before a
    # subprocess is dispatched. Rename alone does not persist its directory.
    if os.name == 'posix':
        directory_fd = os.open(str(path.parent), os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


def _mcp_reservation_capability(row, lease, *, dispatch_id=None, action_id=None):
    """Capture this row and lease generation; never hydrate authority from JSON."""
    def reserve(tool):
        with _LOCK:
            if lease is None or getattr(lease, 'closed', False) or _LEASES.get(row['id']) is not lease or row['id'] not in _ACTIVE:
                raise mcp_budget.DispatchRefused({
                    'nextAction': 'provider_authority_lost',
                    'reason': 'Preparation lease no longer authorizes MCP dispatch.',
                    'wakeCondition': 'explicit_owner_reconciliation'})
            try:
                attempt = mcp_budget.reserve(row, tool, dispatch_id=dispatch_id, action_id=action_id)
                _write(row)
                return attempt
            except mcp_budget.DispatchRefused:
                raise
            except Exception as exc:
                raise mcp_budget.DispatchRefused({
                    'nextAction': 'provider_budget_persistence_failed',
                    'reason': f'MCP dispatch intent could not be persisted: {exc}',
                    'wakeCondition': 'explicit_owner_reconciliation'}) from exc
    return reserve


def _read(run_id: str) -> dict[str, Any]:
    if len(run_id) != 32 or any(c not in '0123456789abcdef' for c in run_id):
        raise ValueError('Invalid preparation ID')
    return json.loads((_directory() / (run_id + '.json')).read_text(encoding='utf-8'))


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
    # The browser only needs the durable stage projection.  Do not wait on the
    # mutable Ghidra coordinator for that read: a long JVM call can hold the
    # interpreter long enough to make an otherwise healthy live dashboard look
    # frozen.  Each receipt is atomically replaced by _write(), so this path
    # either reads the last complete revision or skips a revision being written.
    if public:
        rows: list[dict[str, Any]] = []
        try:
            paths = sorted(_directory().glob('*.json'), key=lambda path: path.stat().st_mtime, reverse=True)[:100]
        except OSError:
            paths = []
        for path in paths:
            try:
                row = json.loads(path.read_text())
            except (OSError, ValueError, TypeError):
                continue
            if not isinstance(row, dict) or not row.get('id'):
                continue
            _ensure_stages(row)
            command = _read_control(str(row['id']))
            if 'deadline' in command:
                row['deadline'] = command['deadline']
                row['budgetSeconds'] = command.get('budgetSeconds', row.get('budgetSeconds'))
                row['budgetOrigin'] = command.get('budgetOrigin', row.get('budgetOrigin', 'default'))
            row['queuePriority'] = command.get('priority', row.get('queuePriority', 50))
            row['priorityReason'] = command.get('priorityReason', 'FIFO among projects with equal priority.')
            rows.append(row)
        waiting = sorted((row for row in rows if row.get('admissionPending') and _read_control(str(row['id'])).get('operation') not in {'pause', 'stop'}), key=_admission_order)
        positions = {str(row['id']): index + 1 for index, row in enumerate(waiting)}
        for row in rows:
            row['queuePosition'] = positions.get(str(row['id']))
        from .actions.jobs import list_jobs
        return [_public_run(row, detailed=row.get('status') in {'running', 'queued', 'paused'}, live_jobs=list_jobs(compact=True)) for row in rows]

    from .actions import jobs
    with _LOCK:
        rows = []
        for path in sorted(_directory().glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:100]:
            row = json.loads(path.read_text())
            job = jobs.get_job(row.get('jobId', ''))
            if row['id'] in _ACTIVE and job and job.status in {'cancelled', 'failed'}:
                _ACTIVE.discard(row['id'])
            _ensure_stages(row)
            if row['id'] not in _ACTIVE and not _owner_alive(row) and row['status'] in {'queued', 'running'}:
                row['status'] = 'interrupted'
                for stage in row['stages']:
                    if stage['status'] == 'running':
                        stage.update(status='interrupted', reason='The server stopped before this stage recorded completion.')
            command = _read_control(row['id'])
            if 'deadline' in command:
                row['deadline'] = command['deadline']
                row['budgetSeconds'] = command.get('budgetSeconds', row.get('budgetSeconds'))
                row['budgetOrigin'] = command.get('budgetOrigin', row.get('budgetOrigin', 'default'))
            row['queuePriority'] = command.get('priority', row.get('queuePriority', 50))
            row['priorityReason'] = command.get('priorityReason', 'FIFO among projects with equal priority.')
            rows.append(row)
        waiting = sorted((row for row in rows if row.get('admissionPending') and _read_control(row['id']).get('operation') not in {'pause', 'stop'}), key=_admission_order)
        positions = {row['id']: index + 1 for index, row in enumerate(waiting)}
        for row in rows:
            row['queuePosition'] = positions.get(row['id'])
        return [_public_run(row, detailed=row.get('status') in {'running', 'queued', 'paused'}) for row in rows] if public else rows


def _admission_order(row: dict[str, Any]) -> tuple[int, float, str]:
    command = _read_control(row['id'])
    return (-int(command.get('priority', row.get('queuePriority', 50))), float(row.get('createdAt', 0)), row['id'])


def _inventory_request(run_id: str) -> dict[str, Any]:
    try:
        return json.loads((_directory() / 'inventory' / (run_id + '.json')).read_text())
    except (OSError, ValueError):
        return {}


def inventory_changed(locator: str) -> dict[str, Any]:
    """Durably admit newly imported members, including during an active wave."""
    context = _project_context({'locator': locator})
    run_id = _context_id(context)
    request = {'id': run_id, 'locator': context['locator'], 'generation': uuid.uuid4().hex, 'updatedAt': time.time()}
    directory = _directory() / 'inventory'
    directory.mkdir(exist_ok=True)
    temporary = directory / (run_id + '.' + request['generation'] + '.tmp')
    temporary.write_text(json.dumps(request))
    temporary.replace(directory / (run_id + '.json'))
    with _LOCK:
        _start_admission_worker()
    return {'id': run_id, 'status': 'accepted', 'inventoryGeneration': request['generation']}


def _collect_inventory_admissions() -> None:
    # Requests have a separate atomic file so an executing wave cannot overwrite
    # a concurrent import notification with its in-memory receipt.
    for path in sorted((_directory() / 'inventory').glob('*.json'), key=lambda path: path.stat().st_mtime, reverse=True)[:100]:
        request = {}
        try:
            request = json.loads(path.read_text())
            row = _read(request['id'])
        except FileNotFoundError:
            if request.get('locator'):
                submit({'locator': request['locator']}, resume=True, _admit=True)
            continue
        except (OSError, ValueError):
            continue
        if row.get('inventoryGeneration') == request.get('generation') or row['id'] in _ACTIVE:
            continue
        if row.get('status') in {'queued', 'running', 'paused'} and _owner_alive(row) and not row.get('admissionPending'):
            continue
        command = _read_control(row['id'])
        if command.get('operation') in {'pause', 'stop'} or row.get('status') == 'cancelled':
            continue
        if _budget_expired(command.get('deadline', row.get('deadline'))):
            continue
        submit({'locator': request['locator']}, resume=True, _admit=True)


def _start_admission_worker() -> None:
    global _ADMISSION_THREAD
    if _ADMISSION_THREAD is None or not _ADMISSION_THREAD.is_alive():
        _ADMISSION_THREAD = threading.Thread(target=_drain_admissions, name='workflow-admission', daemon=True)
        _ADMISSION_THREAD.start()
    _ADMISSION_WAKE.set()


def _drain_admissions() -> None:
    while True:
        _ADMISSION_WAKE.wait(30)
        _ADMISSION_WAKE.clear()
        with _LOCK:
            if len(_ACTIVE) >= 4:
                continue
            pending = sorted((_read(key) for key in list(_WAITING)), key=_admission_order)
            for row in pending:
                if len(_ACTIVE) >= 4:
                    break
                command = _read_control(row['id'])
                if command.get('operation') == 'pause':
                    # A paused admission was silently skipped, so Pause looked
                    # like it did nothing: the row kept its pre-pause status
                    # while no child was ever started.  Checkpoint it visibly
                    # instead.  admissionPending stays true because the
                    # admission really is still pending, and the id stays in
                    # _WAITING so an explicit resume re-admits it in queue
                    # order.  No child is started and no ownership is released.
                    if row.get('status') != 'paused':
                        row.update(status='paused')
                        row.setdefault('events', []).append({
                            'at': time.time(), 'stage': '',
                            'message': 'Paused before admission; no child process was started.',
                        })
                        row['events'] = row['events'][-250:]
                        _write(row)
                    continue
                if command.get('operation') == 'stop' or _budget_expired(command.get('deadline', row.get('deadline'))):
                    row.update(status='cancelled' if command.get('operation') == 'stop' else 'budget-stop', admissionPending=False)
                    _write(row)
                    _WAITING.discard(row['id'])
                    continue
                try:
                    submit({key: row.get(key, '') for key in ('locator', 'program', 'slug')}, resume=True, _admit=True)
                except (OSError, ValueError) as exc:
                    row.update(status='blocked', admissionPending=False, error=str(exc))
                    _write(row)
                    _WAITING.discard(row['id'])
            try:
                _collect_inventory_admissions()
            except (OSError, ValueError):
                # A temporarily inaccessible project remains durably requested.
                pass


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


def _execution_program_bindings(locator: str, info: dict[str, Any], programs: list[str]) -> dict[str, tuple[str, str]]:
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
    rows, _ = query_db('SELECT source_path, locator, program FROM program_binding ORDER BY updated DESC')
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
    for root in (live_root(), _directory().parent):
        if root:
            base = Path(root)
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


def _context_id(context: dict[str, Any]) -> str:
    key = json.dumps([str(live_db()), str(context.get('locator') or ''), str(context.get('program') or ''), str(context.get('slug') or '')])
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def _merge_legacy_contexts(previous: dict[str, Any], locator: str, canonical_id: str) -> dict[str, Any] | None:
    if not locator:
        return None
    candidates = []
    for path in sorted(_directory().glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:100]:
        try:
            legacy = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if legacy.get('id') == canonical_id or _project_context(legacy).get('locator') != locator or legacy.get('supersededBy'):
            continue
        candidates.append(legacy)
    for legacy in candidates:
        if legacy.get('status') in {'running', 'queued', 'paused'} and _owner_alive(legacy):
            return legacy
    preserve_deadline = 'deadline' in previous
    for legacy in candidates:
        previous['createdAt'] = min(previous.get('createdAt', legacy['createdAt']), legacy['createdAt'])
        if legacy.get('deadline') and not preserve_deadline:
            previous['deadline'] = min(previous.get('deadline', legacy['deadline']), legacy['deadline'])
        # Only a known executable fingerprint can carry evidence between old
        # selection-specific admissions. Do not adopt uncertain child actions.
        for program, checkpoint in legacy.get('checkpoints', {}).items():
            fingerprint = checkpoint.get('programFingerprint')
            if not fingerprint:
                continue
            saved = previous.setdefault('checkpoints', {}).get(program)
            if saved is None:
                previous['checkpoints'][program] = checkpoint
            elif saved.get('programFingerprint') == fingerprint:
                previous['checkpoints'][program] = {**checkpoint, **saved}
        legacy['supersededBy'] = canonical_id
        legacy['supersededReason'] = 'Project navigation now joins one project workflow. Original outcomes remain recorded.'
        _write(legacy)
    return None


def submit(context: dict[str, Any], *, resume: bool = False, _admit: bool = False) -> dict[str, Any]:
    context = _project_context(context)
    key = json.dumps([str(live_db()), str(context.get('locator') or ''), str(context.get('program') or ''), str(context.get('slug') or '')])
    run_id = hashlib.sha256(key.encode()).hexdigest()[:32]
    with _LOCK:
        if run_id in _ACTIVE:
            result = _read(run_id)
            return {**result, **({'providerBudget': mcp_budget.public(result)} if 'providerBudget' in result else {})}
        lease = (_directory() / (run_id + '.lock')).open('a+')
        try:
            _lock_lease(lease)
        except BlockingIOError:
            lease.close()
            for _ in range(20):
                try:
                    result = _read(run_id)
                    return {**result, **({'providerBudget': mcp_budget.public(result)} if 'providerBudget' in result else {})}
                except FileNotFoundError:
                    time.sleep(0.01)
            return {'id': run_id, 'status': 'queued', 'locator': context.get('locator', ''),
                    'program': context.get('program', ''), 'slug': context.get('slug', ''),
                    'stages': [], 'events': [], 'reason': 'Another server is recording this preparation admission.'}
        _LEASES[run_id] = lease
        try:
            result = _submit(context, resume=resume, _admit=_admit)
            return {**result, **({'providerBudget': mcp_budget.public(result)} if 'providerBudget' in result else {})}
        finally:
            if run_id not in _ACTIVE:
                _release_lease(run_id)


def _release_lease(run_id: str) -> None:
    with _LOCK:
        lease = _LEASES.pop(run_id, None)
        if lease is not None:
            lease.close()


def _submit(context: dict[str, Any], *, resume: bool = False, _admit: bool = False) -> dict[str, Any]:
    from .actions import jobs

    if not isinstance(resume, bool):
        raise ValueError('resume must be a boolean')
    locator = str(context.get('locator') or '')
    program = str(context.get('program') or '')
    slug = str(context.get('slug') or '')
    if not locator and not slug:
        raise ValueError('Open a project or select a registered binary first.')
    key = json.dumps([str(live_db()), locator, program, slug])
    run_id = hashlib.sha256(key.encode()).hexdigest()[:32]
    with _LOCK:
        list_runs()
        path = _directory() / (run_id + '.json')
        if path.exists():
            previous = _read(run_id)
            live_legacy = _merge_legacy_contexts(previous, locator, run_id)
            if live_legacy:
                return live_legacy
            if _ensure_stages(previous):
                previous['workflowVersion'] = VERSION
            if previous['status'] in {'queued', 'running'} and not _owner_alive(previous):
                previous['status'] = 'interrupted'
                # A coordinator may be restarted while a child job is in a
                # session-critical Ghidra call.  Those child receipts inherit
                # the parent owner in the compact history view, so leaving
                # them as ``running`` makes the renewed coordinator wait on
                # a process that no longer exists.  Preserve their recorded
                # parameters and output, but make their state explicit so
                # retry policy can reconcile their terminal receipt before replay.
                for action_row in (previous.get('actions') or {}).values():
                    if isinstance(action_row, dict) and action_row.get('status') in {'submitting', 'queued', 'running', 'cancelling'}:
                        action_row['status'] = 'interrupted'
                        action_row['interruptedAt'] = time.time()
                        action_row['interruptedReason'] = 'Coordinator restarted before this action recorded completion.'
            _write(previous)
            if run_id in _ACTIVE or (_owner_alive(previous) and previous['status'] in {'queued', 'running'} and not (_admit and previous.get('admissionPending'))) or (not resume and previous['status'] not in {'interrupted'}):
                return previous
        else:
            previous = {}
            live_legacy = _merge_legacy_contexts(previous, locator, run_id)
            if live_legacy:
                return live_legacy
        row = {'id': run_id, 'locator': locator, 'program': program, 'slug': slug,
               'status': 'queued', 'scope': 'project' if locator and not program else 'binary', 'ownerPid': os.getpid(), 'ownerStart': _process_start(os.getpid()), 'ownerHost': socket.gethostname(),
               'createdAt': previous.get('createdAt', time.time()),
               'updatedAt': time.time(), 'workflowVersion': VERSION,
               'queuePriority': _read_control(run_id).get('priority', previous.get('queuePriority', 50)),
               'budgetSeconds': previous.get('budgetSeconds', max(1, previous['deadline'] - previous['createdAt']) if previous.get('deadline') and previous.get('createdAt') else DEFAULT_BUDGET_SECONDS),
               'inventoryGeneration': _inventory_request(run_id).get('generation'),
               'deadline': previous.get('deadline'),
               'budgetOrigin': previous.get('budgetOrigin', 'default'),
               'actions': previous.get('actions', {}), 'jobTimingContexts': previous.get('jobTimingContexts', {}),
               'retryDecisions': previous.get('retryDecisions', {}),
               'events': previous.get('events', []), 'programs': [], 'checkpoints': previous.get('checkpoints', {}),
               'stages': _merge_stages(previous)}
        if 'objectiveBudget' in previous:
            row['objectiveBudget'] = previous['objectiveBudget']
        if 'providerBudget' in previous:
            row['providerBudget'] = previous['providerBudget']
        mcp_budget.initialize(row, context.get('maxMcpToolCalls'))
        admission_budget.initialize(row, context.get('maxActionAdmissions'))
        if resume:
            _reset_resume_projection(row)
        if len(_ACTIVE) >= 4 or (_WAITING and not _admit):
            row.update(admissionPending=True, reason='Waiting for another project operation to release a worker.')
            _write(row)
            _WAITING.add(run_id)
            _start_admission_worker()
            return row
        row['admissionPending'] = False
        _WAITING.discard(run_id)
        _write(row)
        _ACTIVE.add(run_id)
        from .actions.catalog import action_by_id
        try:
            spec = action_by_id('workbench.prepare')
            if spec is None:
                raise ValueError('Preparation action is unavailable.')
            job = jobs.STORE.start(spec, {'locator': locator, 'program': program, 'slug': slug, 'preparation_id': run_id}, ['workbench.prepare'])
            row['jobId'] = job.id
        except Exception as exc:
            _ACTIVE.discard(run_id)
            row.update(status='blocked', error=str(exc))
        _write(row)
        return row


def execute(params: dict[str, Any], cancel: threading.Event) -> tuple[int, str]:
    from .actions import jobs
    from agentdecompile_recovery.corpus.ghidra_project import inspect_locator

    run_id = params['preparation_id']
    with _LOCK:
        row = _read(run_id)
        admission_budget.initialize(row, row.get('maxActionAdmissions'))
        mcp_budget.initialize(row, row.get('maxMcpToolCalls'))
        mcp_lease = _LEASES.get(run_id)
        _ensure_stages(row)
        row['status'] = 'running'
        _write(row)
    comparison_inputs: dict[str, Any] = {}

    def update(key: str, status: str, reason: str = '', **values: Any) -> None:
        with _LOCK:
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
            stage.update(status=status, reason=reason, **values)
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
            _write(row)

    def stopped() -> bool:
        command = _read_control(run_id)
        if 'deadline' in command:
            row['deadline'] = command['deadline']
            row['budgetSeconds'] = command.get('budgetSeconds', row['budgetSeconds'])
        while command.get('operation') == 'pause' and not cancel.is_set():
            row['status'] = 'paused'
            _write(row)
            if _budget_expired(row.get('deadline')):
                return True
            cancel.wait(1)
            command = _read_control(run_id)
            if 'deadline' in command:
                row.update(deadline=command['deadline'], budgetSeconds=command.get('budgetSeconds', row['budgetSeconds']))
        if row['status'] == 'paused':
            row['status'] = 'running'
            _write(row)
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
        with _LOCK:
            history = row.setdefault('actions', {})
            prior = (_matching_retry_prior(history, action_id, fields) if name == 'corpus.match-pair'
                     else dict(history.get(action_id, {})))
        if prior.get('status') == 'ok' and not (prior.get('result') or {}).get('ownershipUnresolved') and (probe or key in {'facts', 'calibrate-global', 'verify-byte-accuracy'}):
            prior = {}
        if not probe and prior.get('status') == 'ok' and not (prior.get('result') or {}).get('ownershipUnresolved') and key not in {'facts', 'calibrate-global', 'verify-byte-accuracy'}:
            return prior['result']
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
            with _LOCK:
                history[action_id] = prior
                _write(row)
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
        with _LOCK:
            history.setdefault(action_id, dict(prior))['retryDecision'] = decision
            if retry_basis is not None:
                history[action_id].update(action=name, params=fields, retryBasis=retry_basis)
            _remember_retry_decision(row, action_id, name, decision)
            _write(row)
        if decision['nextAction'] != 'dispatch':
            update(key, 'waiting' if available else 'blocked', decision['reason'],
                   nextAction=decision['nextAction'], wakeCondition=decision['wakeCondition'],
                   retryDecision=decision, attempts=decision['attemptsSpent'])
            return refusal_outcome(prior, decision)
        for attempt in range(int(prior.get('attempts', 0)), MAX_ACTION_ATTEMPTS):
            # Matching submits several independent candidates into the shared
            # job store. A pause must freeze that admission queue, while a
            # child already executing gets to write its durable receipt.
            if name == 'corpus.match-pair' and _read_control(run_id).get('operation') == 'pause':
                return pause_outcome()
            if stopped():
                raise InterruptedError('Workflow stopped or its execution budget was reached.')
            with _LOCK:
                provider_decision = mcp_budget.exhausted(row) if name.startswith('mcp.') else None
                if provider_decision:
                    _remember_retry_decision(row, action_id, name, provider_decision)
                    _write(row)
                    update(key, 'blocked', provider_decision['reason'], nextAction=provider_decision['nextAction'], wakeCondition=provider_decision['wakeCondition'], retryDecision=provider_decision)
                    return refusal_outcome(prior, provider_decision)
                dispatch_id = uuid.uuid4().hex
                objective_decision = admission_budget.reserve(row, dispatch_id, action_id, name)
                if objective_decision['nextAction'] != 'dispatch':
                    history.setdefault(action_id, {})['retryDecision'] = objective_decision
                    _remember_retry_decision(row, action_id, name, objective_decision)
                    _write(row)
                    update(key, 'blocked', objective_decision['reason'],
                           nextAction=objective_decision['nextAction'],
                           wakeCondition=objective_decision['wakeCondition'], retryDecision=objective_decision)
                    return refusal_outcome(prior, objective_decision)
                history[action_id] = {
                    'dispatchId': dispatch_id,
                    'status': 'submitting', 'action': name, 'params': fields,
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
                _write(row)
            mcp_reserve = _mcp_reservation_capability(row, mcp_lease, dispatch_id=dispatch_id, action_id=action_id)
            job_fields = dict(fields)
            if name == 'corpus.match-pair':
                # This records the project's explicit budget decision with
                # the child receipt. The subprocess remains cancellable; only
                # an Unlimited project avoids the generic 30-minute cutoff.
                job_fields['_preparationUnlimited'] = row.get('deadline') is None
                job_fields['progress_json'] = True
            if key == 'facts' and name == 'mcp.execute-script':
                response, status = jobs._start_preparation_facts_inventory(job_fields, context, _mcp_reserve=mcp_reserve)
            elif fields.get('_preparationProbe') and name == 'mcp.execute-script':
                response, status = jobs._start_preparation_probe(job_fields, context, _mcp_reserve=mcp_reserve)
            else:
                response, status = jobs.start_job(name, job_fields, context=context, confirm=True, **({"_mcp_reserve": mcp_reserve} if name.startswith("mcp.") else {}))
            if status >= 400:
                outcome = {'ok': False, 'error': response.get('error')}
            else:
                job_id = response['job']['id']
                with _LOCK:
                    admission_budget.acknowledge(row, dispatch_id, job_id)
                    history[action_id].update(status='queued', jobId=job_id)
                    checkpoint = row['checkpoints'].get(context.get('program', ''), {})
                    row.setdefault('jobTimingContexts', {})[job_id] = {key: checkpoint.get(key) for key in ('architecture', 'ghidraVersion', 'workSize', 'toolchain')}
                    row['jobTimingContexts'][job_id].update(actionId=name, createdAt=time.time())
                    _write(row)
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
                    command = _read_control(run_id)
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
                            jobs.cancel_job(job_id)
                            drain_deadline = time.monotonic() + 120
                            while job is not None and job.status in {'queued', 'running', 'cancelling'}:
                                if time.monotonic() > drain_deadline:
                                    raise InterruptedError('Queued comparison did not drain while honoring pause.')
                                time.sleep(.25)
                                job = jobs.get_job(job_id)
                            outcome = pause_outcome(job_id)
                            with _LOCK:
                                history[action_id].update(status='paused', result=outcome)
                                _write(row)
                            return outcome
                    elif stopped():
                        jobs.cancel_job(job_id)
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
                        jobs.cancel_job(job_id)
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
                        with _LOCK:
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
                        with _LOCK:
                            row['jobTimingContexts'][job_id].update(status=job.status, startedAt=job.started_at, finishedAt=job.finished_at)
                        outcome = {'ok': job.status == 'ok', 'data': data, 'log': text[-4000:], 'jobId': job_id, 'finishedAt': job.finished_at, 'error': job.error, 'unknownOutcome': job.status == 'interrupted', 'ownershipUnresolved': getattr(job, 'resource_disposition', '') == 'quarantined' or _unresolved_job_ownership(data)}
                        break
                    cancel.wait(.25)
            with _LOCK:
                history[action_id].update(status='ok' if outcome['ok'] else 'failed', result=outcome)
                _write(row)
            provider_decision = outcome.get('data')
            if isinstance(provider_decision, dict) and str(provider_decision.get('nextAction', '')).startswith('provider_'):
                decision = {k: provider_decision[k] for k in ('nextAction', 'reason', 'wakeCondition', 'attemptsSpent', 'attemptsRemaining', 'allocationRevision') if k in provider_decision}
                decision.setdefault('attemptsSpent', mcp_budget.initialize(row)['consumed'])
            else:
                decision = decide_retry(history[action_id], transient=transient_failure(outcome))
            with _LOCK:
                history[action_id]['retryDecision'] = decision
                _remember_retry_decision(row, action_id, name, decision)
                _write(row)
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
            legacy = row['checkpoints'].pop(leaf)
            current = row['checkpoints'].get(program)
            if isinstance(legacy, dict):
                row['checkpoints'][program] = {
                    **legacy,
                    **(current if isinstance(current, dict) else {}),
                }
        execution_routes = _execution_program_bindings(locator, info, programs)
        execution_locator = locator
        execution_programs = {program: execution_routes[program][1] for program in programs}
        execution_locators = {program: execution_routes[program][0] for program in programs}
        _supersede_obsolete_probe_routes(row, execution_routes)
        row['executionLocator'] = execution_locator
        row['executionProgramPaths'] = execution_programs
        row['executionRoutes'] = {program: {'locator': execution_locators[program], 'program': execution_programs[program]} for program in programs}
        if len(programs) > 256:
            raise ValueError('Select at most 256 programs per preparation run.')
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
                checkpoint = row['checkpoints'].setdefault(program, {})
                # A protection refresh must not discard a previously accepted
                # analysis receipt.  The analysis stage decides whether a
                # changed input needs work; preserving this flag makes resume
                # reuse completed programs instead of starting them again.
                if _discard_unverified_probe(checkpoint, execution_program):
                    update('protection', 'running', f'Recording fresh program evidence for {program}.')
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
                if not _accept_probe(checkpoint, execution_program, payload):
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
                    checkpoint['protection'] = observed
                    prepared += 1
                    update('protection', 'running', f'{program}: no protection detected.', completed=prepared, total=len(programs))
                    continue
                prior = checkpoint.get('protection') or {}
                if prior.get('handling') == 'unpacked' and prior.get('receiptPath') and Path(prior['receiptPath']).is_file():
                    checkpoint['protection'] = prior
                    protection_blocked.add(program)
                    prepared += 1
                    continue
                derived = prepare_protected_binary(source, live_root() or _directory())
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
                    if not _accept_probe(checkpoint, execution_program, payload):
                        update('analysis', 'blocked', f'{program}: the Ghidra probe returned a different program path; analysis was not accepted.')
                        continue
                if checkpoint.get('needsAnalysis') is False:
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
            'WHERE EXISTS (SELECT 1 FROM func WHERE func.binary_id=b.id)'
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
            checkpoint = row['checkpoints'].setdefault(program, {})
            binding_key = (locator.replace('\\', '/').rstrip('/'), program.replace('\\', '/').lstrip('/'))
            canonical_source = str((Path(locator).expanduser() / program.lstrip('/')).resolve(strict=False))
            existing = inventory_by_binding.get(binding_key) or inventory_by_source.get(canonical_source)
            if existing:
                checkpoint.update(
                    factsComplete=True, binaryId=existing[0], slug=existing[1],
                    repoPath=existing[2], workSize=existing[3], factsReused=True,
                    recoveryFamily=_effective_recovery_family(existing[4], existing[5], existing[6], existing[0]),
                )
                extracted += 1
                update('facts', 'running', f"{program}: reusing {existing[3]} stored functions.", completed=extracted, total=len(analyzed_programs))
                continue
            facts_path = _directory() / f"{run_id}-{hashlib.sha256(program.encode()).hexdigest()[:12]}.facts"
            checkpoint.pop('programFingerprint', None)
            config = {'db': str(live_db()), 'locator': locator, 'program': program,
                      'slug': row['slug'] if len(programs) == 1 else '', 'factsPath': str(facts_path)}
            code = _inventory_script(config)
            result = action('facts', 'mcp.execute-script', {'programPath': execution_programs[program], 'code': code, 'timeout': 600}, {**row, 'locator': execution_locators[program], 'program': execution_programs[program]})
            payload = result.get('data') or {}
            if result['ok'] and isinstance(payload, dict) and payload.get('inventoryAvailable'):
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
        )
        if error:
            legacy_records, legacy_error = query_db(
                'SELECT id,slug,repo_path,recovery_family,func_count,arch,bits FROM binary '
                'WHERE EXISTS (SELECT 1 FROM func WHERE func.binary_id=binary.id)'
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
                checkpoint = row['checkpoints'].setdefault(program, {})
                configured = os.environ.get('AGENT_DECOMPILE_BSIM_URL', '').strip()
                fingerprint = checkpoint.get('programFingerprint') or ''
                identity = hashlib.sha256(json.dumps([locator, program, fingerprint]).encode()).hexdigest()[:24]
                bsim_file = _directory().parent / 'bsim' / 'corpus' / 'signatures'
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
        row['comparisonTargets'] = [{'source': src, 'target': dst, 'reason': note} for src, dst, note in pairs]
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
        comparison_inputs.update(_matching_input_digests({path for src, dst, _ in pairs for path in (src, dst)}, input_progress))
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
        row['comparisonTargets'] = [{'source': src, 'target': dst, 'reason': note, 'recoveryFamily': family_by_path.get(src)} for src, dst, note in pairs]
        row['excludedComparisonTargets'] = excluded_pairs
        row['comparisonTargetsFrozenAt'] = time.time()
        row['comparisonInputs'] = comparison_inputs
        update('matching', 'running', 'Comparison targets and input evidence frozen.', completed=0, total=len(pairs), progressUnit='comparisons', workProgress=None)
        _write(row)
        if not pairs:
            update('matching', 'blocked', 'No other binary has stored function features to compare. Import or analyze a comparison binary.')
        else:
            matched = 0
            admitted = 0
            deferred = 0
            to_run = []
            for src, dst, note in pairs:
                existing = read_comparison_receipt(run_id, src, dst, comparison_inputs)
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
                result = action('matching', 'corpus.match-pair', {'db': str(live_db()), 'src': src, 'dst': dst, 'run': f'prepare-{run_id}', 'note': note}, row)
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
                                    record_comparison_receipt(run_id, src, dst, result, comparison_inputs)
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
            if _read_control(run_id).get('operation') == 'pause':
                update('matching', 'paused', f'Paused after {matched} of {len(pairs)} durable comparison receipts.', completed=matched, total=len(pairs), deferred=len(pairs) - matched)
                raise _PauseRequested()
            update('matching', 'completed' if matched == len(pairs) else 'partial', f'{matched} of {len(pairs)} pairs compared. {deferred} comparisons await admission.' if deferred else f'{matched} of {len(pairs)} pairs compared.', completed=matched, total=len(pairs), deferred=deferred)
        if pairs and matched:
            merged = action('matching', 'workbench.merge-evidence', {'db': str(live_db()), 'run': f'prepare-{run_id}'}, row)
            update('matching', 'completed' if merged['ok'] and matched == len(pairs) else 'partial', 'Compared identities bound; existing human metadata retained.' if merged['ok'] else merged.get('error') or 'Knowledge binding could not finish.', completed=matched, total=len(pairs))
        from .workflow import continue_recovery
        recovery_families: dict[str, list[str]] = {}
        for program in programs:
            checkpoint = row['checkpoints'].get(program, {})
            family = str(checkpoint.get('recoveryFamily') or f"unclassified:{checkpoint.get('binaryId') or hashlib.sha256(program.encode()).hexdigest()[:12]}")
            checkpoint['recoveryFamily'] = family
            recovery_families.setdefault(family, []).append(program)
        family_receipts = row.setdefault('recoveryFamilies', {})
        for family, members in sorted(recovery_families.items()):
            eligible = [program for program in members if row['checkpoints'].get(program, {}).get('analysisConfirmed') and row['checkpoints'].get(program, {}).get('factsComplete')]
            family_receipts[family] = {
                'family': family, 'programs': members, 'eligiblePrograms': eligible,
                'state': 'running' if eligible else 'waiting', 'updatedAt': time.time(),
            }
            if eligible:
                continue_recovery(
                    row, _directory().parent, live_db(), action, update,
                    execution_routes=execution_routes, recovery_family=family,
                    programs=eligible, all_programs=programs,
                )
            else:
                family_receipts[family]['reason'] = 'Waiting for this family\'s analysis and facts receipts.'
        _write(row)
        routed = sum(bool(execution_locators[program] and execution_programs[program]) for program in programs)
        probed = sum(
            _same_program_path(row['checkpoints'].get(program, {}).get('observedProgramPath'), execution_programs[program])
            for program in programs
        )
        row['executionSummary'] = {'programs': len(programs), 'routed': routed, 'probed': probed}
        if programs and (not routed or not probed):
            row.update(
                status='blocked',
                error=(
                    'No executable Ghidra project route was found for this preparation.'
                    if not routed else
                    'No program probe receipt matched its requested Ghidra program; no execution evidence was accepted.'
                ),
            )
        else:
            row['status'] = 'completed' if all(stage['status'] == 'completed' for stage in row['stages']) else 'partial'
    except _PauseRequested:
        row.update(status='paused', error='')
    except InterruptedError as exc:
        row.update(status='cancelled' if cancel.is_set() else 'budget-stop', error=str(exc))
    except Exception as exc:
        row.update(status='blocked', error=str(exc))
    finally:
        with _LOCK:
            provider_block = next((stage for stage in row['stages'] if str(stage.get('nextAction', '')).startswith('provider_')), None)
            if provider_block is not None:
                row.update(status='blocked', error=provider_block.get('reason', 'MCP dispatch budget blocked this preparation.'))
            for stage in row['stages']:
                if stage['status'] in {'running', 'queued', 'waiting', 'cancelling'}:
                    stage.update(status='blocked', reason=row.get('error') or 'A prerequisite prevented this stage from running.')
            _write(row)
            _ACTIVE.discard(run_id)
            _release_lease(run_id)
            _ADMISSION_WAKE.set()
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


def _comparison_path(run_id: str, src: str, dst: str) -> Path:
    if len(run_id) != 32 or any(c not in '0123456789abcdef' for c in run_id):
        raise ValueError('Invalid preparation ID')
    key = hashlib.sha256(json.dumps([str(live_db()), src, dst]).encode()).hexdigest()
    return _directory() / 'comparisons' / run_id / (key + '.json')


def _matching_input_digests(paths: set[str], progress: Any = None) -> dict[str, Any]:
    """Hash matcher inputs once per binary per wave, in one SQLite snapshot."""
    if not paths:
        return {}
    result = {}
    if progress:
        progress(0, len(paths))
    with sqlite3.connect(f'{Path(live_db()).resolve().as_uri()}?mode=ro', uri=True) as con:
        con.row_factory = sqlite3.Row
        con.execute('BEGIN')
        available = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
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
            add({'schema': 'matcher-input-v1', 'binary': dict(binary)})
            for row in con.execute('SELECT * FROM func WHERE binary_id=? ORDER BY addr,id', (binary['id'],)):
                add({'func': dict(row)})
                count += 1
                if progress and count % 5000 == 0:
                    progress(len(result), len(paths), source, count)
            if 'calledge' in available:
                for row in con.execute('SELECT caller_addr,callee_addr FROM calledge WHERE binary_id=? ORDER BY caller_addr,callee_addr', (binary['id'],)):
                    add({'edge': list(row)})
            if 'decomp' in available:
                for row in con.execute('SELECT addr,n_tokens,n_lines,max_nest,n_calls,n_locals,n_deref,n_index,n_field,ctrl,ops,skeleton_hash FROM decomp WHERE binary_id=? AND ok=1 ORDER BY addr', (binary['id'],)):
                    add({'decomp': dict(row)})
            result[source] = {'source': source, 'schema': 'matcher-input-v1', 'digest': digest.hexdigest(), 'functionCount': count, 'md5': binary['md5']}
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


def record_comparison_receipt(run_id: str, src: str, dst: str, result: dict[str, Any], inputs: dict[str, Any] | None = None) -> None:
    """Persist a completed shared job, with no byte-verification claim."""
    if not result.get('ok') or not result.get('jobId'):
        raise ValueError('A completed comparison job is required.')
    path = _comparison_path(run_id, src, dst)
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {'preparationId': run_id, 'db': str(live_db()), 'source': src, 'target': dst,
               'jobId': result['jobId'], 'jobStatus': 'ok', 'completedAt': result.get('finishedAt'),
               'result': result.get('data'), 'claim': 'advisory', 'scope': 'completed-pair-comparison',
               'inventory': _comparison_inventory(src, dst, inputs),
               'freshnessLimit': 'Inputs are frozen once per matching wave. Later changes to function metadata, features, call edges, or decompilation metrics invalidate reuse on the next wave.'}
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(receipt), encoding='utf-8')
    temporary.replace(path)


def read_comparison_receipt(run_id: str, src: str, dst: str, inputs: dict[str, Any] | None = None) -> dict[str, Any] | None:
    try:
        receipt = json.loads(_comparison_path(run_id, src, dst).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if receipt.get('jobStatus') != 'ok' or receipt.get('source') != src or receipt.get('target') != dst or receipt.get('db') != str(live_db()) or receipt.get('preparationId') != run_id:
        return None
    if receipt.get('inventory') != _comparison_inventory(src, dst, inputs):
        return None
    return receipt


def _control_path(run_id: str) -> Path:
    if len(run_id) != 32 or any(c not in '0123456789abcdef' for c in run_id):
        raise ValueError('Invalid preparation ID')
    directory = _directory() / 'controls'
    directory.mkdir(exist_ok=True)
    return directory / (run_id + '.json')


def _read_control(run_id: str) -> dict[str, Any]:
    try:
        value = json.loads(_control_path(run_id).read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _revise_admission_budget(run_id: str, params: dict[str, Any], *, provider: bool = False) -> dict[str, Any]:
    # An active coordinator owns a long-lived row snapshot. Require its existing
    # lease to drain so neither its heartbeat nor its next intent can lose this
    # revision. The OS lease also fences other server processes.
    allocation = 'maxMcpToolCalls' if provider else 'maxActionAdmissions'
    label = 'MCP provider' if provider else 'Admission'
    accounting = mcp_budget if provider else admission_budget
    with _LOCK:
        _read(run_id)  # Validate identity before constructing its lease path.
        if run_id in _ACTIVE or run_id in _LEASES:
            raise ValueError(f'Pause and drain the preparation before changing its {label.lower()} allocation')
        with (_directory() / (run_id + '.lock')).open('a+') as lease:
            try:
                _lock_lease(lease)
            except BlockingIOError as exc:
                raise ValueError('Preparation is owned by an active coordinator; pause and drain before revising') from exc
            row = _read(run_id)
            if allocation not in params and params.get('unlimited') is not True:
                raise ValueError(f'Supply {allocation} or explicit unlimited=true')
            accounting.revise(
                row, expected_revision=params.get('expectedAllocationRevision'),
                maximum=params.get(allocation), unlimited=params.get('unlimited', False))
            _write(row)
        _ADMISSION_WAKE.set()
        queued = (run_id in _WAITING or bool(row.get('admissionPending'))) and _read_control(run_id).get('operation') not in {'pause', 'stop'}
        return {**_public_run(row), 'controlAcknowledged': True,
                'nextAction': 'wait_for_admission' if queued else 'resume',
                'wakeCondition': 'admission_capacity' if queued else 'explicit_resume',
                'reason': (f'{label} allocation revised without changing spending; existing queued work remains eligible.' if queued else
                           f'{label} allocation revised without changing spending; resume the preparation to continue.')}


def control(params: dict[str, Any]) -> dict[str, Any]:
    """Shared pause/stop/budget controls, independent of the browser lifecycle."""
    run_id = str(params.get('preparation_id') or '')
    operation = str(params.get('operation') or '')
    if operation in {'admission-budget', 'provider-budget'}:
        return _revise_admission_budget(run_id, params, provider=operation == 'provider-budget')
    if operation not in {'pause', 'resume', 'stop', 'budget', 'priority'}:
        raise ValueError('Choose pause, resume, stop, budget, or priority.')
    with _LOCK:
        row = _read(run_id)
        command = _read_control(run_id)
        if operation == 'priority':
            value = params.get('priority')
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
                raise ValueError('Priority must be an integer from 0 to 100; higher values run first.')
            command.update(priority=value, priorityReason=f'Operator priority {value}; applies to waiting admission, without interrupting active work.')
        elif operation == 'budget':
            value = params.get('seconds')
            if params.get('unlimited') is True:
                value = None
            if 'seconds' not in params and params.get('unlimited') is not True:
                raise ValueError('Supply seconds:null for unlimited, or 1 to 604800 seconds.')
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_BUDGET_SECONDS):
                raise ValueError('Budget must be null for unlimited, or 1 to 604800 seconds.')
            command.update(deadline=time.time() + value if value is not None else None, budgetSeconds=value, budgetOrigin='explicit')
        else:
            command['operation'] = operation
        command['updatedAt'] = time.time()
        path = _control_path(run_id)
        temporary = path.with_name(path.name + f'.{os.getpid()}.{threading.get_ident()}.tmp')
        temporary.write_text(json.dumps(command))
        temporary.replace(path)
        _ADMISSION_WAKE.set()
    # Pause takes effect between stages. An accepted native operation is allowed
    # to drain; releasing its project lock early would risk duplicated mutations.
    may_resume = operation == 'resume' or (operation == 'budget' and row['status'] == 'budget-stop' and command.get('operation') not in {'pause', 'stop'})
    # A paused coordinator has drained its accepted child and released its
    # lease. Its server process can still be alive, so owner liveness alone
    # must not prevent a durable resume of the same receipt.
    if may_resume and run_id not in _ACTIVE and (not _owner_alive(row) or row['status'] not in {'running', 'queued'}):
        if 'deadline' in command:
            row.update(deadline=command['deadline'], budgetSeconds=command.get('budgetSeconds'))
            _write(row)
        return submit({key: row.get(key, '') for key in ('locator', 'program', 'slug')}, resume=True)
    return {**row, 'providerBudget': _public_run(row).get('providerBudget'), 'objectiveBudget': _public_run(row).get('objectiveBudget'), 'deadline': command.get('deadline', row.get('deadline')), 'budgetSeconds': command.get('budgetSeconds', row.get('budgetSeconds')), 'queuePriority': command.get('priority', row.get('queuePriority', 50)), 'priorityReason': command.get('priorityReason', 'FIFO among projects with equal priority.'), 'control': command, 'controlAcknowledged': True}


def recover_interrupted() -> list[dict[str, Any]]:
    """Resume admissions whose owner is confirmed dead; never touch live owners."""
    recovered = []
    with _LOCK:
        _start_admission_worker()
    for row in sorted(list_runs(), key=_admission_order):
        if row.get('supersededBy') or row.get('status') != 'interrupted' or _owner_alive(row):
            continue
        if _read_control(row['id']).get('operation') in {'pause', 'stop'}:
            continue
        if _budget_expired(row.get('deadline')):
            continue
        recovered.append(submit({key: row.get(key, '') for key in ('locator', 'program', 'slug')}, resume=True, _admit=True))
    return recovered
