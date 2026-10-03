"""Owned synthetic lifecycle fixtures; no compiler, corpus DB, or service."""
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

import pytest

from agentdecompile_recovery.corpus import cross_place as cp
from agentdecompile_recovery.corpus import cross_place_admission as gate
from agentdecompile_recovery.corpus import cross_place_checkpoint as checkpoint
from agentdecompile_recovery.corpus import supervision
from agentdecompile_recovery.corpus.dashboard.actions import jobs, job_history


@pytest.fixture
def scope(tmp_path, monkeypatch):
    receipts = tmp_path / 'receipts'; receipts.mkdir()
    monkeypatch.setattr(job_history, 'directory', lambda: receipts)
    monkeypatch.setattr(job_history, 'owner', lambda: {'ownerPid': os.getpid(), 'ownerStart': 'fixture'})
    out = tmp_path / 'output'; out.mkdir()
    (out / 'donor').mkdir()
    (out / 'donor/leaf.c').write_text('int leaf(void){return 7;}')
    db = tmp_path / 'fixture.sqlite'; db.write_bytes(b'not opened by lifecycle tests')
    raw = tmp_path / 'raw'; raw.mkdir()
    receipt = out / 'receipt.json'; receipt.write_text('{}')
    params = {'from': 'donor', 'repo': '/donor.exe', 'db': str(db), 'out-dir': str(out),
              'raw-dir': str(raw), 'byteexact-receipt': str(receipt), 'watch': True}
    store = jobs.JobStore()
    yield tmp_path, receipts, params, store
    for fd in list(store._cross_leases.values()):
        os.close(fd)
    store._cross_leases.clear()
    if store._resource_owner_handle: store._resource_owner_handle.close()


def retained(scope, *, phase='dispatch-possible', owner=True, memory=False):
    root, receipts, params, store = scope
    with gate.output_owner(params['out-dir'], [Path(params['db'])]) as area:
        ledger = checkpoint.Ledger(area)
        source = Path(params.get('source-dir') or Path(params['out-dir']) / 'donor')
        source_info = source.stat()
        checkpoint.save(ledger.root / 'scan.json', {'schema': checkpoint.SCHEMA,
            'scope': {'source': str(source), 'device': source_info.st_dev, 'inode': source_info.st_ino,
                'parameters': {'repo': params['repo'], 'db': params['db'],
                'raw': params['raw-dir'], 'receipt': params['byteexact-receipt'], 'exploration': False}}})
        envelope = {'version': 1, 'generation': 'a' * 32,
                    'lease': gate.lease_envelope(params['out-dir']),
                    'scanDigest': hashlib.sha256((ledger.root / 'scan.json').read_bytes()).hexdigest()}
        job = jobs.JobRecord(id='a' * 12, action_id='corpus.cross-place', title='fixture',
            params=params, argv=cp.guarded_command(params, envelope), execution_root=str(root),
            execution_attempt=envelope['generation'], status='running',
            resource_keys={'external': [['output', str(area)]]}, resource_disposition='held',
            cross_place_generation={'version': 1, 'phase': phase, 'generation': envelope['generation'],
                                    'envelope': envelope, 'priorClearance': None})
        if owner: job.execution_owner = {'pid': 123456, 'start_ticks': 'fixture', 'boot_id': 'fixture'}
        row = {**job.to_dict(), 'receiptVersion': 1}
        (receipts / (job.id + '.json')).write_text(json.dumps(row))
        if memory:
            store._cross_leases[job.id] = os.dup(gate.lease_fds()[0])
            job.status = 'failed'  # Terminal in memory, receipt commit failed.
            job.resource_disposition = 'quarantined'
            store._jobs[job.id] = job
    return job, row


def test_restored_nonterminal_generation_requires_fresh_clearance(scope, monkeypatch):
    job, row = retained(scope)
    store = scope[3]
    monkeypatch.setattr(supervision, 'session_clearance', lambda owner: 'occupied')
    refused = store.reconcile_resources(job.id)
    assert not refused['eligible'] and 'fresh_whole_session_clearance' in refused['missingEvidence']
    assert json.loads((scope[1] / (job.id + '.json')).read_text()) == row
    assert store._external_held
    seen = []
    def clear(owner):
        seen.append(owner); return 'clear'
    monkeypatch.setattr(supervision, 'session_clearance', clear)
    result = store.reconcile_resources(job.id)
    assert result['released'] and seen == [row['executionOwner']]
    saved = json.loads((scope[1] / (job.id + '.json')).read_text())
    assert saved['status'] == 'failed' and saved['finishedAt'] and saved['resourceDisposition'] == 'released'
    assert jobs._bound_clearance(saved) and not store._external_held


@pytest.mark.parametrize('phase', ['intent', 'undispatched'])
def test_restored_explicit_undispatched_generation_needs_no_owner(scope, monkeypatch, phase):
    job, _ = retained(scope, phase=phase, owner=False)
    monkeypatch.setattr(supervision, 'session_clearance', lambda _: pytest.fail('No child was dispatched'))
    assert scope[3].reconcile_resources(job.id)['released']
    saved = json.loads((scope[1] / (job.id + '.json')).read_text())
    assert saved['status'] == 'cancelled' and not saved['executionOwner']
    assert jobs._cross_place_not_dispatched(saved)


def test_unknown_dispatch_cannot_borrow_predecessor_clearance(scope, monkeypatch):
    job, row = retained(scope, owner=False)
    monkeypatch.setattr(supervision, 'session_clearance', lambda _: pytest.fail('Unknown owner is not a process identity'))
    result = scope[3].reconcile_resources(job.id)
    assert not result['eligible'] and 'observed_generation_owner' in result['missingEvidence']
    assert scope[3]._external_held
    assert json.loads((scope[1] / (job.id + '.json')).read_text()) == row


def test_terminal_save_failure_retains_physical_lease_until_cross_thread_repair(scope, monkeypatch):
    import fcntl
    job, row = retained(scope, memory=True)
    store = scope[3]; descriptor = store._cross_leases[job.id]
    lock = Path(scope[2]['out-dir']) / gate.AREA / '.owner.lock'
    monkeypatch.setattr(supervision, 'session_clearance', lambda _: 'clear')
    actual_save = supervision.save_state
    with monkeypatch.context() as patch:
        patch.setattr(supervision, 'save_state', lambda *_: (_ for _ in ()).throw(OSError('durable terminal refused')))
        with pytest.raises(OSError, match='durable terminal refused'): store.reconcile_resources(job.id)
    assert os.fstat(descriptor) and store._external_held
    assert json.loads((scope[1] / (job.id + '.json')).read_text()) == row
    with lock.open('a+') as competitor:
        with pytest.raises(BlockingIOError): fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    outcomes = queue.Queue()
    def repair():
        try: outcomes.put(store.reconcile_resources(job.id))
        except BaseException as exc: outcomes.put(exc)
    thread = threading.Thread(target=repair); thread.start(); thread.join(timeout=5)
    assert not thread.is_alive()
    result = outcomes.get_nowait(); assert isinstance(result, dict) and result['released'], result
    assert not store._external_held and job.id not in store._cross_leases
    with pytest.raises(OSError): os.fstat(descriptor)
    with lock.open('a+') as competitor:
        fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert supervision.save_state is actual_save


@pytest.mark.parametrize('callback', ['started', 'output', 'clearance'])
def test_real_postspawn_callback_failure_never_abandons_owned_session(tmp_path, callback):
    owners = []; cleared = []
    def started(owner):
        owners.append(owner)
        if callback == 'started': raise OSError('started receipt failed')
    def output(text):
        if callback == 'output':
            assert len(text) <= 4096  # Unterminated output is drained in bounded chunks.
            raise OSError('output receipt failed')
    def clearance(owner):
        cleared.append(owner)
        if callback == 'clearance': raise OSError('clearance receipt failed')
    body = ('import os,time;os.write(1,b"x"*262144);time.sleep(30)' if callback == 'output'
            else 'import time;time.sleep(30)' if callback == 'started'
            else 'print("finished",flush=True)')
    code, log = jobs._default_executor([sys.executable, '-I', '-S', '-c', body], tmp_path,
        threading.Event(), on_started=started, on_output=output, on_clearance=clearance, timeout_seconds=5)
    assert code == 124 and 'callback/setup failure' in log
    assert len(owners) == 1 and supervision.session_clearance(owners[0]) == 'clear'
    assert cleared == owners
    assert ('ownership remains unresolved' in log) == (callback == 'clearance')


def test_pre_spawn_cancellation_records_no_dispatch_without_popen(tmp_path, monkeypatch):
    cancel = threading.Event(); cancel.set(); seen = []
    monkeypatch.setattr(jobs.subprocess, 'Popen', lambda *a, **k: pytest.fail('Cancelled command spawned'))
    code, log = jobs._default_executor([sys.executable, '-I', '-S', '-c', 'pass'], tmp_path, cancel,
                                     on_not_started=lambda: seen.append('undispatched'))
    assert code == 1 and 'cancelled before spawn' in log and seen == ['undispatched']


def test_live_runner_borrow_blocks_reconciliation_even_after_status_error(scope, monkeypatch):
    job, _ = retained(scope, memory=True)
    store = scope[3]; store._cross_active.add(job.id)
    monkeypatch.setattr(supervision, 'session_clearance', lambda _: pytest.fail('Still owned by active runner'))
    result = store.reconcile_resources(job.id)
    assert not result['eligible'] and 'live_executor_terminal' in result['missingEvidence']
    assert job.id in store._cross_leases
    store._cross_active.remove(job.id)


def test_preparing_receipt_reconciles_without_inventing_worker(scope, monkeypatch):
    job, _ = retained(scope, owner=False)
    job.argv = cp.guarded_command(job.params)
    job.cross_place_generation = {'version': 1, 'phase': 'preparing',
                                  'binding': jobs._cross_place_preparation_binding(job.to_dict())}
    row = {**job.to_dict(), 'receiptVersion': 1}
    (scope[1] / (job.id + '.json')).write_text(json.dumps(row))
    monkeypatch.setattr(supervision, 'session_clearance', lambda _: pytest.fail('Preparing is not a spawned worker'))
    assert scope[3].reconcile_resources(job.id)['released']


@pytest.mark.parametrize('change', ['lease', 'scan', 'generation'])
def test_changed_restored_generation_scope_never_releases(scope, monkeypatch, change):
    job, row = retained(scope, phase='intent', owner=False)
    if change == 'lease':
        lock = Path(scope[2]['out-dir']) / gate.AREA / '.owner.lock'
        lock.rename(lock.with_name('old-owner.lock'))
        lock.write_bytes(b'replaced inode')
    elif change == 'scan':
        scan = Path(scope[2]['out-dir']) / gate.AREA / 'checkpoint/scan.json'
        scan.write_bytes(scan.read_bytes() + b' ')
    else:
        row['executionAttempt'] = 'b' * 32
        (scope[1] / (job.id + '.json')).write_text(json.dumps(row))
    monkeypatch.setattr(supervision, 'session_clearance', lambda _: pytest.fail('Invalid scope cannot observe or release'))
    result = scope[3].reconcile_resources(job.id)
    assert not result['eligible'] and scope[3]._external_held


@pytest.mark.parametrize('change', ['path', 'device', 'replaced-directory', 'symlink'])
def test_restored_scan_source_identity_is_current_and_canonical(scope, monkeypatch, change):
    job, row = retained(scope)
    source = Path(scope[2]['out-dir']) / 'donor'
    scan_path = Path(scope[2]['out-dir']) / gate.AREA / 'checkpoint/scan.json'
    scan = checkpoint.read(scan_path)
    if change == 'path':
        scan['scope']['source'] = str(source / '..' / 'donor')
        checkpoint.save(scan_path, scan)
    elif change == 'device':
        scan['scope']['device'] += 1
        checkpoint.save(scan_path, scan)
    else:
        moved = source.with_name('previous-donor')
        source.rename(moved)
        if change == 'symlink': source.symlink_to(moved, target_is_directory=True)
        else:
            source.mkdir()
            (source / 'leaf.c').write_bytes((moved / 'leaf.c').read_bytes())
    before = (scope[1] / (job.id + '.json')).read_bytes()
    monkeypatch.setattr(supervision, 'session_clearance', lambda _: pytest.fail('Source scope must refuse before process observation'))
    result = scope[3].reconcile_resources(job.id)
    reason = 'exact_checkpoint_source_path' if change in ('path', 'symlink') else 'exact_checkpoint_source_identity'
    assert not result['eligible'] and reason in result['missingEvidence']
    assert scope[3]._external_held and (scope[1] / (job.id + '.json')).read_bytes() == before


@pytest.mark.parametrize('marker_mode', ['complete', 'malformed', 'missing'])
def test_silent_survivor_pipe_retains_session_without_stranding_reader(tmp_path, marker_mode):
    """Own/reap the grandchild even when its final readiness proof is invalid."""
    import ctypes
    import signal
    import time
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0
    assert libc.prctl(36, 1, 0, 0, 0) == 0
    ready = tmp_path / 'survivor-ready.json'
    spawned_path = tmp_path / 'survivor-spawned.json'
    child = f"""import json,os,time
from pathlib import Path
pid=os.getpid()
start=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]
ready=Path({str(ready)!r})
if {marker_mode!r}!='missing':
    raw=json.dumps({{'pid':pid,'start_ticks':start}}) if {marker_mode!r}=='complete' else '{{"pid":'
    temporary=ready.with_suffix('.tmp')
    temporary.write_text(raw)
    temporary.replace(ready)
time.sleep(30)
"""
    leader = f"""import json,subprocess,sys,time
from pathlib import Path
p=subprocess.Popen([sys.executable,'-I','-S','-c',{child!r}])
try:
    start=Path('/proc/'+str(p.pid)+'/stat').read_text().rsplit(')',1)[1].split()[19]
    identity={{'pid':p.pid,'start_ticks':start}}
    fallback=Path({str(spawned_path)!r})
    temporary=fallback.with_suffix('.tmp')
    temporary.write_text(json.dumps(identity));temporary.replace(fallback)
    print(json.dumps({{'event':'survivor-spawned','identity':identity}}),flush=True)
    deadline=time.monotonic()+3
    ready=Path({str(ready)!r})
    while not ready.exists():
        if time.monotonic()>deadline: raise RuntimeError('survivor startup deadline')
        time.sleep(.01)
    proof=json.loads(ready.read_text())
    if (not isinstance(proof,dict) or type(proof.get('pid')) is not int
            or not isinstance(proof.get('start_ticks'),str)
            or not proof['start_ticks'].isdigit() or proof!=identity):
        raise RuntimeError('survivor readiness identity mismatch')
except BaseException:
    try: p.kill()
    except ProcessLookupError: pass
    p.wait(timeout=2)
    raise
print('survivor-ready',flush=True)
"""
    owners = []; clear = []; known = {}; before_threads = set(threading.enumerate())
    def remember(identity):
        if (not isinstance(identity, dict) or type(identity.get('pid')) is not int
                or identity['pid'] <= 0 or not isinstance(identity.get('start_ticks'), str)
                or not identity['start_ticks'].isdigit()):
            raise AssertionError('Invalid fixture cleanup identity')
        known[(identity['pid'], identity['start_ticks'])] = identity
    def collect(log):
        for line in log.splitlines():
            try: event = json.loads(line)
            except ValueError: continue  # A chunk may end before the newline.
            if isinstance(event, dict) and event.get('event') == 'survivor-spawned':
                remember(event['identity'])
    try:
        started = time.monotonic()
        code, log = jobs._default_executor([sys.executable, '-I', '-S', '-c', leader], tmp_path,
            threading.Event(), on_started=owners.append, on_output=collect,
            on_clearance=clear.append, timeout_seconds=8)
        collect(log)
        assert time.monotonic() - started < 8
        assert len(owners) == 1 and known
        if marker_mode == 'complete':
            assert code == 124 and 'ownership remains unresolved' in log
            assert ready.is_file() and not clear
            assert supervision.session_clearance(owners[0]) == 'occupied'
        else:
            assert code != 0 and 'ownership remains unresolved' not in log
            assert clear == owners and supervision.session_clearance(owners[0]) == 'clear'
            assert 'JSONDecodeError' in log if marker_mode == 'malformed' else 'startup deadline' in log
        readers = [t for t in threading.enumerate() if t not in before_threads
                   and (t.name.startswith('agentdecompile-output-')
                        or getattr(getattr(t, '_target', None), '__name__', '') == 'read')]
        assert not readers, 'Executor returned while its pipe reader was still alive'
    finally:
        try:
            # Cleanup never parses the readiness proof. The leader publishes
            # this complete identity before waiting, and also streams it so
            # failure of the on-disk fallback cannot discard an observed PID.
            if not known and spawned_path.exists():
                remember(json.loads(spawned_path.read_text()))
            for identity in known.values():
                pid = identity['pid']
                if supervision.process_identity(pid).get('start_ticks') == identity['start_ticks']:
                    try: os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                deadline = time.monotonic() + 3
                while True:
                    try: reaped, _ = os.waitpid(pid, os.WNOHANG)
                    except ChildProcessError: break
                    if reaped: break
                    if time.monotonic() > deadline: raise AssertionError('Owned survivor was not reaped')
                    time.sleep(.01)
        finally:
            assert libc.prctl(36, previous.value, 0, 0, 0) == 0


@pytest.mark.parametrize('change', ['unchanged', 'replaced', 'symlink', 'missing', 'fallback-scan'])
def test_restored_explicit_source_root_never_falls_back(scope, monkeypatch, change):
    source = scope[0] / 'external-source'
    source.mkdir()
    (source / 'leaf.c').write_text('int leaf(void){return 7;}')
    scope[2]['source-dir'] = str(source)
    job, _ = retained(scope, phase='intent', owner=False)
    receipt_path = scope[1] / (job.id + '.json')
    before = receipt_path.read_bytes()
    if change in ('replaced', 'symlink', 'missing'):
        previous = source.with_name('original-external-source')
        source.rename(previous)
        if change == 'replaced':
            source.mkdir()
            (source / 'leaf.c').write_bytes((previous / 'leaf.c').read_bytes())
        elif change == 'symlink':
            source.symlink_to(previous, target_is_directory=True)
    elif change == 'fallback-scan':
        scan_path = Path(scope[2]['out-dir']) / gate.AREA / 'checkpoint/scan.json'
        scan = checkpoint.read(scan_path)
        fallback = Path(scope[2]['out-dir']) / 'donor'
        info = fallback.stat()
        scan['scope'].update(source=str(fallback), device=info.st_dev, inode=info.st_ino)
        checkpoint.save(scan_path, scan)
    monkeypatch.setattr(supervision, 'session_clearance',
                        lambda _: pytest.fail('Undispatched explicit root needs no process observation'))
    result = scope[3].reconcile_resources(job.id)
    if change == 'unchanged':
        assert result['released'], result
        saved = json.loads(receipt_path.read_text())
        assert saved['status'] == 'cancelled' and saved['resourceDisposition'] == 'released'
        assert not saved['executionOwner'] and jobs._cross_place_not_dispatched(saved)
        assert not scope[3]._external_held
    else:
        reasons = {'replaced': 'exact_checkpoint_source_identity',
                   'symlink': 'exact_checkpoint_source_path',
                   'missing': 'readable_bound_generation_scope',
                   'fallback-scan': 'exact_checkpoint_source_path'}
        assert not result['eligible'] and reasons[change] in result['missingEvidence'], result
        assert scope[3]._external_held and receipt_path.read_bytes() == before
