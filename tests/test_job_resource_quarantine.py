"""Isolated JobStore boundary tests; no game/tool subprocess or server."""
import json
import threading
from unittest.mock import Mock

_REAL_THREAD_START = threading.Thread.start

import pytest

from agentdecompile_recovery.corpus.dashboard.actions import jobs, job_history
from agentdecompile_recovery.corpus.dashboard.actions.catalog import ActionSpec


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, 'directory', lambda: tmp_path / 'workbench-jobs')
    monkeypatch.setattr(job_history, 'owner', lambda: {'ownerPid': 1, 'ownerStart': 'test'})
    monkeypatch.setattr(jobs, 'live_root', lambda: tmp_path)
    # Exercise synchronously, without background writer/cancel threads.
    monkeypatch.setattr(threading.Thread, 'start', lambda _: None)
    action = ActionSpec(id='corpus.fake', title='Fake', group='corpus', backend='corpus-cli',
                        command='fake', identity_scope='database', ghidra_exclusive=True)
    monkeypatch.setattr(jobs, 'action_by_id', lambda _: action)
    return tmp_path, action


def insert(store, action, db, job_id='123456789abc', **params):
    job = jobs.JobRecord(id=job_id, action_id=action.id, title='Fake', argv=[],
                         params={'db': str(db), 'locator': 'project', **params})
    store._jobs[job.id] = job
    store._order.append(job.id)
    return job


def test_unknown_exit_retains_locks_frees_worker_and_survives_restart(sandbox):
    root, action = sandbox
    store = jobs.JobStore()
    job = insert(store, action, root / 'db')
    store.executor = lambda *a: (124, '[process did not reach a terminal state; ownership remains unresolved]')
    store._run(job.id, threading.Event())
    assert job.resource_disposition == 'quarantined'
    assert store._running == 0
    assert store._identity_held[str(root / 'db')] == job.id
    assert job.to_dict()['ownershipUnresolved']
    store._resource_owner_handle.close()  # simulate old coordinator exit
    restored = jobs.JobStore()
    restored._restore_reservations_locked()
    assert restored._identity_held == store._identity_held
    assert restored._ghidra_held == store._ghidra_held
    assert jobs._from_history(json.loads((root / 'workbench-jobs' / (job.id + '.json')).read_text())).resource_disposition == 'quarantined'


def test_conflicting_admission_waits_but_independent_db_proceeds(sandbox, monkeypatch):
    root, action = sandbox
    action = ActionSpec(id=action.id, title='Fake', group='corpus', backend='corpus-cli', command='fake', identity_scope='database')
    monkeypatch.setattr(jobs, 'action_by_id', lambda _: action)
    store = jobs.JobStore()
    store._restore_reservations_locked()
    store._identity_held[str(root / 'db')] = 'old-owner'
    blocked = insert(store, action, root / 'db')
    cancel = threading.Event()
    monkeypatch.setattr(jobs.time, 'sleep', lambda _: cancel.set())
    executor = Mock(return_value=(0, '{}'))
    store.executor = executor
    store._run(blocked.id, cancel)
    executor.assert_not_called()
    healthy = insert(store, action, root / 'other', 'abcdef123456')
    store._run(healthy.id, threading.Event())
    assert executor.call_count == 1
    assert healthy.resource_disposition == 'released'
    assert store._identity_held[str(root / 'db')] == 'old-owner'


def test_intent_is_durable_before_executor_and_exception_quarantines(sandbox):
    root, action = sandbox
    store = jobs.JobStore()
    job = insert(store, action, root / 'db')
    def executor(*args):
        receipt = json.loads((root / 'workbench-jobs' / (job.id + '.json')).read_text())
        assert receipt['resourceDisposition'] == 'held'
        assert receipt['resourceKeys']['identity'] == str(root / 'db')
        raise RuntimeError('lost outcome after dispatch')
    store.executor = executor
    store._run(job.id, threading.Event())
    assert job.resource_disposition == 'quarantined'
    assert store._identity_held[str(root / 'db')] == job.id


def test_corrupt_receipt_prevents_scoped_dispatch(sandbox):
    root, action = sandbox
    folder = root / 'workbench-jobs'
    folder.mkdir()
    (folder / 'bad.json').write_text('{broken')
    store = jobs.JobStore()
    job = insert(store, action, root / 'db')
    store.executor = Mock()
    store._run(job.id, threading.Event())
    store.executor.assert_not_called()
    assert 'Cannot reconcile' in job.error


def test_readonly_status_bypass_requires_actual_boolean(sandbox, monkeypatch):
    root, _ = sandbox
    action = ActionSpec(id='corpus.recovery-orchestrator', title='Supervisor', group='corpus',
                        backend='corpus-cli', command='recovery-orchestrator', identity_scope='database', ghidra_exclusive=True)
    monkeypatch.setattr(jobs, 'action_by_id', lambda _: action)
    assert jobs._resource_keys(action, {'db': str(root / 'db'), 'status': 'true'})
    assert jobs._resource_keys(action, {'db': str(root / 'db'), 'status': True}) == {}
    store = jobs.JobStore()
    store._restore_reservations_locked = Mock(side_effect=AssertionError('status must not restore/admit resources'))
    job = insert(store, action, root / 'db', status=True)
    store.executor = Mock(return_value=(0, '{}'))
    store._run(job.id, threading.Event())
    assert store.executor.call_count == 1
    assert job.resource_disposition == 'unreserved'


def test_terminal_store_failure_keeps_reservation(sandbox, monkeypatch):
    root, action = sandbox
    from agentdecompile_recovery.corpus import supervision
    original = supervision.save_state
    def write(path, payload):
        if payload.get('resourceDisposition') == 'released':
            raise OSError('store lost')
        original(path, payload)
    monkeypatch.setattr(supervision, 'save_state', write)
    store = jobs.JobStore()
    job = insert(store, action, root / 'db')
    store.executor = lambda *a: (0, '{}')
    store._run(job.id, threading.Event())
    assert job.resource_disposition == 'quarantined'
    assert store._identity_held[str(root / 'db')] == job.id
    saved = json.loads((root / 'workbench-jobs' / (job.id + '.json')).read_text())
    assert saved['resourceDisposition'] == 'held'


def test_legacy_interrupted_record_restores_resource(sandbox):
    root, action = sandbox
    folder = root / 'workbench-jobs'
    folder.mkdir()
    (folder / '123456789abc.json').write_text(json.dumps({'id': '123456789abc', 'actionId': action.id,
        'status': 'interrupted', 'params': {'db': str(root / 'db'), 'locator': 'project'}}))
    store = jobs.JobStore()
    store._restore_reservations_locked()
    assert store._identity_held[str(root / 'db')] == '123456789abc'


def test_late_async_snapshot_cannot_overwrite_new_durable_intent(sandbox, monkeypatch):
    root, action = sandbox
    store = jobs.JobStore()
    job = insert(store, action, root / 'db')
    store._persist_locked(job, force=True)
    old = dict(store._persist_pending)
    class Interleave(dict):
        def items(self):
            job.resource_keys = {'identity': str(root / 'db')}
            job.resource_disposition = 'quarantined'
            store._persist_locked(job, force=True)
            return super().items()
    store._persist_pending = Interleave(old)
    class Wake:
        waits = 0
        def wait(self):
            self.waits += 1
            if self.waits > 1:
                raise StopIteration
        def clear(self):
            pass
    store._persist_wake = Wake()
    obsolete_write = Mock(side_effect=AssertionError('old queued snapshot overwrote quarantine'))
    monkeypatch.setattr(job_history, 'write', obsolete_write)
    with pytest.raises(StopIteration):
        store._persist_loop()
    obsolete_write.assert_not_called()
    saved = json.loads((root / 'workbench-jobs' / (job.id + '.json')).read_text())
    assert saved['resourceDisposition'] == 'quarantined'


def test_verified_release_is_not_restored_as_quarantine(sandbox):
    root, action = sandbox
    store = jobs.JobStore()
    job = insert(store, action, root / 'db')
    store.executor = lambda *a: (0, '{}')
    store._run(job.id, threading.Event())
    assert job.resource_disposition == 'released'
    store._resource_owner_handle.close()  # simulate old coordinator exit
    restored = jobs.JobStore()
    restored._restore_reservations_locked()
    assert not restored._identity_held
    assert not restored._ghidra_held


@pytest.mark.parametrize('log', [
    'progress {"event":"progress"}\nterminal {"ownershipResolved":false}',
    '{"result":"{\\"ownershipResolved\\":false}"}',
    '{"result":{"data":{"ownershipUnresolved":true}}}',
])
def test_nested_or_later_json_cannot_clear_quarantine(log):
    assert jobs._ownership_unresolved(log)


def test_history_owner_death_is_readonly_projection(sandbox, monkeypatch):
    root, action = sandbox
    from agentdecompile_recovery.corpus.dashboard import preparation
    folder = root / 'workbench-jobs'
    folder.mkdir()
    receipt = {'id': '123456789abc', 'actionId': action.id, 'status': 'running',
               'resourceDisposition': 'held', 'resourceKeys': {'identity': str(root / 'db')}}
    path = folder / '123456789abc.json'
    path.write_text(json.dumps(receipt))
    monkeypatch.setattr(job_history, 'live_root', lambda: root)
    monkeypatch.setattr(job_history, '_RECORDS_CACHE', None)
    monkeypatch.setattr(job_history, '_CACHE', {})
    monkeypatch.setattr(preparation, '_owner_alive', lambda _: False)
    monkeypatch.setattr(job_history, 'write', Mock(side_effect=AssertionError('read path rewrote receipt')))
    assert job_history.records()['123456789abc']['status'] == 'interrupted'
    assert json.loads(path.read_text()) == receipt



def test_second_resource_authority_refused(sandbox):
    first = jobs.JobStore()
    first._restore_reservations_locked()
    second = jobs.JobStore()
    with pytest.raises(OSError, match='Another JobStore'):
        second._restore_reservations_locked()


@pytest.mark.parametrize('keys', [{'identity': ''}, {'pair': ['db', {}]}, {}])
def test_invalid_reserved_resource_identity_refuses_admission(sandbox, keys):
    root, action = sandbox
    folder = root / 'workbench-jobs'
    folder.mkdir()
    (folder / '123456789abc.json').write_text(json.dumps({'id': '123456789abc', 'actionId': action.id,
        'status': 'running', 'resourceDisposition': 'held', 'resourceKeys': keys}))
    with pytest.raises(OSError, match='Cannot reconcile'):
        jobs.JobStore()._restore_reservations_locked()


def test_unknown_legacy_action_does_not_drop_reservation(sandbox, monkeypatch):
    root, _ = sandbox
    monkeypatch.setattr(jobs, 'action_by_id', lambda _: None)
    folder = root / 'workbench-jobs'
    folder.mkdir()
    (folder / '123456789abc.json').write_text(json.dumps({'id': '123456789abc', 'actionId': 'unknown',
        'status': 'interrupted', 'params': {}}))
    with pytest.raises(OSError, match='unknown interrupted action'):
        jobs.JobStore()._restore_reservations_locked()


@pytest.mark.parametrize('where', ['project', 'program', 'command'])
def test_remote_unknown_dispatch_propagates_quarantine(sandbox, monkeypatch, where):
    root, _ = sandbox
    from agentdecompile_recovery.corpus.dashboard import mcp_bridge
    action = ActionSpec(id='mcp.execute-script', title='Script', group='mcp', backend='mcp-cli',
                        command='execute-script', mutating=True)
    uncertain = {'ok': False, 'error': 'connection lost', 'ownershipResolved': False,
                 'ownershipUnresolved': True, 'text': '', 'parsed': None}
    monkeypatch.setattr(mcp_bridge, 'ensure_project', lambda *a, **k: uncertain if where == 'project' else {'ok': True})
    monkeypatch.setattr(mcp_bridge, 'ensure_program', lambda *a, **k: uncertain if where == 'program' else {'ok': True})
    monkeypatch.setattr(mcp_bridge, 'call_tool', lambda *a, **k: uncertain)
    code, log = jobs._mcp_executor_in_context(action, {'locator': 'project', 'programPath': 'program'}, threading.Event())
    assert code != 0
    assert jobs._ownership_unresolved(log)


@pytest.mark.parametrize('raises', [False, True])
def test_archive_thread_completion_does_not_clear_remote_unknown(sandbox, monkeypatch, raises):
    root, _ = sandbox
    class InlineThread:
        def __init__(self, *, target, **kwargs):
            self.target = target
        def start(self):
            self.target()
        def is_alive(self):
            return False
    monkeypatch.setattr(jobs.threading, 'Thread', InlineThread)
    def export(*args):
        if raises:
            raise RuntimeError('lost remote outcome')
        return {'ok': False, 'ownershipResolved': False, 'ownershipUnresolved': True}
    monkeypatch.setattr(jobs, '_export_archive_program', export)
    result = jobs._bounded_archive_export(root / 'out', {}, threading.Event(), deadline=999999999999)
    assert result['ownershipResolved'] is False
    assert result['ownershipUnresolved'] is True
    assert not result['ok']


def completed_but_retained(sandbox, monkeypatch):
    root, action = sandbox
    monkeypatch.setattr(jobs, 'LOCAL_RECONCILIATION_ACTIONS', frozenset({action.id}))
    from agentdecompile_recovery.corpus import supervision
    original = supervision.save_state
    failed = False
    def commit_then_fail(path, payload):
        nonlocal failed
        original(path, payload)
        if payload.get('resourceDisposition') == 'released' and not failed:
            failed = True
            raise OSError('directory durability acknowledgment lost')
    monkeypatch.setattr(supervision, 'save_state', commit_then_fail)
    def local_executor(*args, **kwargs):
        identity = {'pid': 12345, 'start_ticks': '42', 'boot_id': 'boot'}
        kwargs['on_started'](identity)
        kwargs['on_clearance'](identity)
        return 1, 'scientific result failed; resources clear'
    monkeypatch.setattr(jobs, '_default_executor', local_executor)
    store = jobs.JobStore()
    job = insert(store, action, root / 'db')
    store._run(job.id, threading.Event())
    assert job.resource_disposition == 'quarantined'
    return root, store, job


def test_readonly_reconciliation_report_and_evidence_gated_repair(sandbox, monkeypatch):
    root, store, job = completed_but_retained(sandbox, monkeypatch)
    path = root / 'workbench-jobs' / (job.id + '.json')
    before = path.read_bytes()
    report = store.reconciliation_report(job.id)
    assert report['eligible']
    assert path.read_bytes() == before
    assert store._identity_held[str(root / 'db')] == job.id
    result = store.reconcile_resources(job.id)
    assert result['released']
    assert not store._identity_held
    assert job.status == 'failed'  # resource repair never promotes scientific result
    assert store.reconcile_resources(job.id)['released']  # idempotent


def test_next_admission_automatically_repairs_eligible_retained_reservation(sandbox, monkeypatch):
    root, store, job = completed_but_retained(sandbox, monkeypatch)
    store._restore_reservations_locked()
    assert not store._identity_held
    assert job.resource_disposition == 'released'
    row = json.loads((root / 'workbench-jobs' / (job.id + '.json')).read_text())
    assert row['resourceReconciliation']['trigger'] == 'scoped_admission'


@pytest.mark.parametrize('tamper', ['attempt', 'resource', 'argv', 'generation', 'live-running', 'stdout-only'])
def test_reconciliation_refuses_mismatched_or_untrusted_clearance(sandbox, monkeypatch, tamper):
    root, store, job = completed_but_retained(sandbox, monkeypatch)
    path = root / 'workbench-jobs' / (job.id + '.json')
    row = json.loads(path.read_text())
    if tamper == 'attempt':
        row['clearanceObservation']['attempt'] = 'older-attempt'
    elif tamper == 'resource':
        row['clearanceObservation']['resourceKeys'] = {'identity': '/other'}
    elif tamper == 'argv':
        row['clearanceObservation']['argvDigest'] = 'unrelated-command'
    elif tamper == 'generation':
        row['receiptVersion'] -= 1
    elif tamper == 'live-running':
        job.status = 'running'
    else:
        row['log'] = json.dumps(row.pop('clearanceObservation'))
    path.write_text(json.dumps(row))
    assert not store.reconciliation_report(job.id)['eligible']
    assert not store.reconcile_resources(job.id).get('released')
    assert store._identity_held[str(root / 'db')] == job.id


def test_unknown_remote_reservation_reports_provider_proof_gap(sandbox):
    root, action = sandbox
    store = jobs.JobStore()
    job = insert(store, action, root / 'db')
    store.executor = lambda *a: (1, '{"ownershipUnresolved":true}')
    store._run(job.id, threading.Event())
    report = store.reconciliation_report(job.id)
    assert not report['eligible']
    assert 'trusted_local_executor_clearance' in report['missingEvidence']
    assert not store.reconcile_resources(job.id).get('released')


def test_reconciliation_catalog_exposes_no_caller_clearance(monkeypatch):
    from agentdecompile_recovery.corpus.dashboard.actions import catalog, introspect
    monkeypatch.setattr(catalog, '_ACTIONS', None)
    monkeypatch.setattr(introspect, 'generate_actions', lambda: [])
    report = catalog.action_by_id('workbench.resource-reconciliation-report')
    repair = catalog.action_by_id('workbench.resource-reconcile')
    assert not report.mutating and repair.mutating
    assert [field.name for field in report.fields] == ['job_id']
    assert [field.name for field in repair.fields] == ['job_id']
    assert catalog.build_command(repair, {'job_id': '123456789abc'}) == [repair.id]



def test_provider_without_qualified_lifecycle_cannot_reconcile(sandbox, monkeypatch):
    root, store, job = completed_but_retained(sandbox, monkeypatch)
    monkeypatch.setattr(jobs, 'LOCAL_RECONCILIATION_ACTIONS', frozenset())
    report = store.reconciliation_report(job.id)
    assert 'qualified_provider_lifecycle_contract' in report['missingEvidence']
    assert not store.reconcile_resources(job.id).get('released')
    assert store._identity_held[str(root / 'db')] == job.id



@pytest.mark.parametrize('after_replace', [False, True])
def test_reconciliation_commit_failure_keeps_live_reservation(sandbox, monkeypatch, after_replace):
    root, store, job = completed_but_retained(sandbox, monkeypatch)
    from agentdecompile_recovery.corpus import supervision
    original = supervision.save_state
    def fail(path, row):
        if after_replace:
            original(path, row)
        raise OSError('reconciliation durability failure')
    monkeypatch.setattr(supervision, 'save_state', fail)
    with pytest.raises(OSError, match='durability failure'):
        store.reconcile_resources(job.id)
    assert job.resource_disposition == 'quarantined'
    assert store._identity_held[str(root / 'db')] == job.id


def test_corrupt_oversized_timestamp_is_reported_not_accepted(sandbox, monkeypatch):
    root, store, job = completed_but_retained(sandbox, monkeypatch)
    path = root / 'workbench-jobs' / (job.id + '.json')
    row = json.loads(path.read_text())
    row['clearanceObservation']['observedAt'] = 10 ** 1000
    path.write_text(json.dumps(row))
    report = store.reconciliation_report(job.id)
    assert not report['eligible']
    assert 'clearance_before_full_action_completion' in report['missingEvidence']


def snapshot_action(monkeypatch):
    from agentdecompile_recovery.corpus.cli import build_parser
    from agentdecompile_recovery.corpus.dashboard.actions.introspect import specs_from_argparse
    action = next(a for a in specs_from_argparse(group="corpus", backend="corpus-cli", parser=build_parser()) if a.id == "corpus.export-reagent-snapshot")
    monkeypatch.setattr(jobs, "action_by_id", lambda _: action)
    return action


def test_only_explicit_action_contract_claims_paths(sandbox, monkeypatch):
    root, ordinary = sandbox
    assert "external" not in jobs._resource_keys(ordinary, {"compiler": "/tool", "destination": "/out"})
    action = snapshot_action(monkeypatch)
    assert "destination" in [f.name for f in action.fields]
    assert jobs._resource_keys(action, {"destination": "out"}) == {"external": [["output", str(root / "out")]]}


def test_snapshot_injected_success_without_proof_quarantines(sandbox, monkeypatch):
    root, _ = sandbox
    action = snapshot_action(monkeypatch)
    store = jobs.JobStore()
    job = insert(store, action, root / "db", destination="out")
    store.executor = lambda *args: (0, '{}')
    store._run(job.id, threading.Event())
    assert job.status == "ok" and job.resource_disposition == "quarantined"
    store._resource_owner_handle.close()
    restored = jobs.JobStore()
    restored._restore_reservations_locked()
    assert restored._external_held == store._external_held


@pytest.mark.parametrize("held", [("store", "out"), ("project", "."), ("output", "out/child")])
def test_cross_kind_tree_overlap_blocks_dispatch(sandbox, monkeypatch, held):
    root, _ = sandbox
    action = snapshot_action(monkeypatch)
    store = jobs.JobStore()
    store._restore_reservations_locked()
    store._external_held[(held[0], str((root / held[1]).resolve()))] = "old-owner"
    job = insert(store, action, root / "db", destination="out")
    cancel = threading.Event()
    monkeypatch.setattr(jobs.time, "sleep", lambda _: cancel.set())
    store.executor = Mock(return_value=(0, '{}'))
    store._run(job.id, cancel)
    store.executor.assert_not_called()


@pytest.mark.parametrize("action_id", ["unknown", "corpus.logical-build"])
def test_unknown_released_external_receipt_retained(sandbox, monkeypatch, action_id):
    root, _ = sandbox
    monkeypatch.setattr(jobs, "action_by_id", lambda _: None)
    folder = root / "workbench-jobs"
    folder.mkdir()
    row = {"id": "123456789abc", "actionId": action_id, "resourceDisposition": "released", "status": "ok",
           "resourceKeys": {"external": [["store", str(root / "out")]]}}
    (folder / (row["id"] + ".json")).write_text(json.dumps(row))
    store = jobs.JobStore()
    store._restore_reservations_locked()
    assert store._external_held[("store", str(root / "out"))] == row["id"]
    assert not store.reconciliation_report(row["id"])["eligible"]


@pytest.mark.parametrize("claim", [["made-up", "/out"], ["output", "relative"], ["output", "/a/../out"]])
def test_bad_restored_external_keys_fail_closed(sandbox, claim):
    root, _ = sandbox
    folder = root / "workbench-jobs"
    folder.mkdir()
    (folder / "123456789abc.json").write_text(json.dumps({"id": "123456789abc", "status": "running",
        "resourceDisposition": "held", "resourceKeys": {"external": [claim]}}))
    store = jobs.JobStore()
    with pytest.raises(OSError, match="Cannot reconcile"):
        store._restore_reservations_locked()
    assert not store._external_held


def test_restore_duplicate_owners_is_atomic(sandbox, monkeypatch):
    root, _ = sandbox
    monkeypatch.setattr(jobs, "action_by_id", lambda _: None)
    folder = root / "workbench-jobs"
    folder.mkdir()
    for job_id in ["123456789abc", "abcdef123456"]:
        (folder / (job_id + ".json")).write_text(json.dumps({"id": job_id, "status": "running",
            "resourceDisposition": "held", "resourceKeys": {"external": [["output", str(root / "out")]]}}))
    store = jobs.JobStore()
    with pytest.raises(OSError, match="Ambiguous"):
        store._restore_reservations_locked()
    assert not store._external_held and not store._identity_held


@pytest.mark.parametrize("destination", ["out", "~/out"])
def test_real_snapshot_executor_release_and_restart(sandbox, monkeypatch, destination):
    import sqlite3
    from pathlib import Path
    root, _ = sandbox
    action = snapshot_action(monkeypatch)
    kb = root / "kb.sqlite"
    with sqlite3.connect(kb) as con:
        con.execute("CREATE TABLE func_knowledge(program TEXT, entry_hex TEXT, decompiled TEXT, asm TEXT)")
        con.execute("INSERT INTO func_knowledge VALUES ('fixture', '00001000', 'void f() {}', 'ret')")
    # Literal cwd/~ exists: passing the raw argument would write there,
    # while expanduser claims the synthetic home below.
    (root / "~").mkdir()
    synthetic_home = root / "home"
    synthetic_home.mkdir()
    monkeypatch.setattr(Path, "expanduser", lambda path: synthetic_home / str(path)[2:] if str(path).startswith("~/") else path)
    expected_output = synthetic_home / "out" if destination.startswith("~") else root / "out"
    params = {"kb": str(kb), "program": "fixture", "address": ["1000"], "destination": destination}
    store = jobs.JobStore()
    job = insert(store, action, kb, **params)
    job.argv = jobs.build_command(action, params)
    # Restore actual thread start only for the real executor's pipe drain.
    monkeypatch.setattr(threading.Thread, "start", _REAL_THREAD_START)
    original = store._restore_reservations_locked
    def change_live_root_after_freeze():
        original()
        monkeypatch.setattr(jobs, "live_root", lambda: root / "changed")
    store._restore_reservations_locked = change_live_root_after_freeze
    store._run(job.id, threading.Event())
    assert job.status == "ok", job.log or job.error
    assert (expected_output / "manifest.json").is_file()
    assert not (root / "~" / "out").exists()
    assert job.params["destination"] == str(expected_output)
    assert job.argv[job.argv.index("--destination") + 1] == str(expected_output)
    assert job.resource_keys["external"] == [["output", str(expected_output)]]
    assert job.execution_root == str(root)
    assert job.resource_disposition == "released"
    assert jobs._bound_clearance(job.to_dict())
    store._resource_owner_handle.close()
    restored = jobs.JobStore()
    restored._restore_reservations_locked()
    assert not restored._external_held


@pytest.mark.parametrize('missing', [True, False])
def test_snapshot_default_executor_requires_matching_owner_clearance(sandbox, monkeypatch, missing):
    root, _ = sandbox
    action = snapshot_action(monkeypatch)
    def executor(*args, **kwargs):
        kwargs['on_started']({'pid': 123, 'start_ticks': '1', 'boot_id': 'boot'})
        if not missing:
            kwargs['on_clearance']({'pid': 456, 'start_ticks': '2', 'boot_id': 'boot'})
        return 0, '{}'
    monkeypatch.setattr(jobs, '_default_executor', executor)
    store = jobs.JobStore()
    job = insert(store, action, root / 'db', destination='out')
    store._run(job.id, threading.Event())
    assert job.resource_disposition == 'quarantined'
