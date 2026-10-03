"""Future authority acceptance cases; source authoring is not executed proof.

Fixtures acquire actual OS leases in isolated temporary namespaces. Child jobs and
provider effects are inert doubles. No fixture grants authority from stored JSON.
Cross-process crash durability and installed-consumer acceptance remain separate.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import threading
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from agentdecompile_recovery.corpus.dashboard import admission_budget, mcp_budget, preparation


def activate(authority):
    with preparation._guard(authority):
        slot = preparation._ExecutionSlot(authority)
        authority.slot = slot
        with preparation._LOCK:
            assert authority.run_id not in preparation._ACTIVE
            preparation._ACTIVE[authority.run_id] = slot
    return authority


def retire(authority):
    preparation._retire_capacity(authority.slot)
    preparation._release_lease(authority.run_id, expectedAuthority=authority)


def resume(authority):
    """Use the real retained healthy witness after exact-token retirement."""
    retire(authority)
    return activate(preparation._acquire_authority(authority.root, authority.db, authority.run_id))


@contextmanager
def authority_environment(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    assert not (root / 'preparations').exists()
    for name in ('_ACTIVE', '_LEASES', '_AUTHORITIES', '_HEALTHY', '_BIRTHS', '_FAULTS',
                 '_NAMESPACE_FAULTS', '_NAMESPACE_LIMITS', '_DIAGNOSTICS',
                 '_NEXT_NAMESPACE_PROBE', '_NEXT_CONTROL_PROBE', '_COMMAND_FAULTS'):
        monkeypatch.setattr(preparation, name, {})
    monkeypatch.setattr(preparation, '_WAITING', set())
    monkeypatch.setattr(preparation, '_SUSPENDED', set())
    monkeypatch.setattr(preparation, '_SESSION', object())
    monkeypatch.setattr(preparation, '_SESSION_ID', '1' * 32)
    monkeypatch.setattr(preparation, '_ADMISSION_WAKE', threading.Event())
    monkeypatch.setattr(preparation, 'live_root', lambda: root)
    monkeypatch.setattr(preparation, 'live_db', lambda: root / 'corpus.sqlite')
    monkeypatch.setattr(preparation, '_start_admission_worker', lambda: None)

    def create(fields=None, *, active=True, db=None):
        values = copy.deepcopy(fields or {})
        run_id = values.pop('id', f'{len(preparation._BIRTHS) + 16:032x}')
        assert not {'authority', 'objectiveBudget', 'providerBudget'} & values.keys()
        birth = preparation._issue_new_objective(root, run_id)
        authority = preparation._acquire_authority(root, db or root / 'corpus.sqlite', run_id, birth=birth)
        # A genuine empty first commit precedes all scenario-specific history.
        with preparation._guard(authority):
            authority.row.update(status='blocked', locator='fixture-project', program='', slug='',
                                 stages=[], events=[], actions={}, checkpoints={}, deadline=None, budgetSeconds=None)
            admission_budget.initialize(authority.row, values.get('maxActionAdmissions'))
            mcp_budget.initialize(authority.row, values.get('maxMcpToolCalls'))
            preparation._write(authority.row, authority=authority, phase='initialization')
            if values:
                authority.row.update(values)
                preparation._write(authority.row, authority=authority)
        return activate(authority) if active else authority

    try:
        yield create
    finally:
        # Only isolated fixture-owned handles. Fault retention is asserted before
        # teardown; this is not a production force-release or repair adapter.
        handles = list(preparation._LEASES.values())
        handles += [authority.lease for authority in preparation._FAULTS.values()]
        for handle in handles:
            if not handle.closed:
                handle.close()


@pytest.fixture
def authority_factory(tmp_path, monkeypatch):
    with authority_environment(tmp_path, monkeypatch) as create:
        yield create


def raw(authority):
    return (authority.directory / (authority.run_id + '.json')).read_bytes()


def reserve_intent(authority, dispatch='dispatch-one'):
    with preparation._guard(authority):
        assert admission_budget.reserve(authority.row, dispatch, 'basis', 'corpus.match-pair')['nextAction'] == 'dispatch'
        preparation._write(authority.row, authority=authority, phase='intent')
    return dispatch


def test_birth_is_durable_single_use_and_healthy_resume_keeps_both_histories(authority_factory):
    authority = authority_factory({'maxActionAdmissions': 3, 'maxMcpToolCalls': 4})
    log = authority.root / '.preparation-authority-births-v1.jsonl'
    records = [json.loads(line) for line in log.read_bytes().splitlines()]
    assert records[0]['kind'] == 'namespace'
    assert records[1] == {'kind': 'objective-issued', 'runId': authority.run_id, 'birthSessionId': '1' * 32}
    assert len(records) == 2 and authority.birth.used
    reserve_intent(authority)
    preparation._mcp_reservation_capability(authority, dispatch_id='dispatch-one', action_id='basis')('read')
    with preparation._guard(authority):
        authority.row['actions']['basis'] = {'attempts': 3, 'status': 'interrupted', 'dispatchId': 'dispatch-one'}
        preparation._write(authority.row, authority=authority)
    saved = copy.deepcopy(authority.committed)
    successor = resume(authority)
    assert successor.generation != authority.generation
    assert successor.row == saved
    with preparation._guard(successor):
        preparation._write(successor.row, authority=successor)
    assert successor.revision == saved['authority']['rowRevision'] + 1
    for key in ('objectiveBudget', 'providerBudget', 'actions'):
        assert successor.row[key] == saved[key]
    assert len(log.read_bytes().splitlines()) == 2
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation._issue_new_objective(authority.root, authority.run_id)


def test_birth_busy_is_no_effect_and_rechecks_after_release(authority_factory):
    healthy = authority_factory()
    root, run_id = healthy.root, 'b' * 32
    path = root / '.preparation-authority-births-v1.jsonl'
    before = path.read_bytes()
    before_births = dict(preparation._BIRTHS)
    with (root / '.preparation-authority-births-v1.lock').open('a+') as held:
        preparation._lock_lease(held)
        with pytest.raises(preparation._PreparationIssuanceWait) as caught:
            preparation._issue_new_objective(root, run_id)
        body, status = preparation.authority_refusal(caught.value)
        assert status == 409
        assert body == {
            'ok': False, 'status': 'waiting',
            'error': 'Preparation namespace issuance is busy; retry after the namespace lock becomes available.',
            'reason': 'Preparation namespace issuance is busy; retry after the namespace lock becomes available.',
            'nextAction': 'preparation_issuance_busy', 'wakeCondition': 'birth_namespace_lock_available',
            'preparationId': run_id, 'generation': None, 'lastCommittedRevision': None,
            'phase': 'initialization', 'durable': False, 'retryable': True,
            'retryAfterSeconds': 1, 'noEffect': True}
        assert path.read_bytes() == before and preparation._BIRTHS == before_births
        assert run_id not in preparation._ACTIVE and run_id not in preparation._LEASES
        assert not preparation._NAMESPACE_FAULTS and not preparation._FAULTS
        assert not (root / 'preparations' / (run_id + '.json')).exists()
        reserve_intent(healthy)  # Existing witnessed work ignores issuance contention.
    witness = preparation._issue_new_objective(root, run_id)
    assert preparation._issue_new_objective(root, run_id) is witness
    assert len(path.read_bytes().splitlines()) == 3


@pytest.mark.parametrize('boundary', ['acquisition_permission', 'append_sync'])
def test_namespace_nonbusy_failures_latch_and_do_not_heal(authority_factory, monkeypatch, boundary):
    healthy = authority_factory()
    root, run_id = healthy.root, 'c' * 32
    path = root / '.preparation-authority-births-v1.jsonl'
    before = path.read_bytes()
    with monkeypatch.context() as patch:
        if boundary == 'acquisition_permission':
            def deny(_handle):
                raise PermissionError('lock descriptor denied')
            patch.setattr(preparation, '_lock_lease', deny)
        else:
            def uncertain(_path):
                raise BlockingIOError('append directory flush uncertain')
            patch.setattr(preparation, '_sync_directory', uncertain)
        with pytest.raises(preparation._PreparationAuthorityRefused) as caught:
            preparation._issue_new_objective(root, run_id)
    assert preparation.authority_refusal(caught.value)[1] == 503
    assert str(root) in preparation._NAMESPACE_FAULTS
    after = path.read_bytes()
    assert (after == before) is (boundary == 'acquisition_permission')
    assert (str(root), run_id) not in preparation._BIRTHS
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation._issue_new_objective(root, 'd' * 32)
    assert path.read_bytes() == after
    reserve_intent(healthy)


@pytest.mark.parametrize('damage', ['partial', 'duplicate-key', 'duplicate-id', 'blank', 'bad-id', 'noncanonical'])
def test_complete_birth_log_validation_never_accepts_valid_prefix(authority_factory, damage):
    healthy = authority_factory()
    log = healthy.root / '.preparation-authority-births-v1.jsonl'
    tails = {
        'partial': b'{', 'duplicate-key': b'{"kind":"objective-issued","kind":"namespace"}\n',
        'duplicate-id': log.read_bytes().splitlines(keepends=True)[1], 'blank': b'\n',
        'bad-id': preparation._birth_record({'kind': 'objective-issued', 'runId': 'ABC', 'birthSessionId': '2' * 32}),
        'noncanonical': b'{ "kind": "namespace" }\n'}
    with log.open('ab') as stream:
        stream.write(tails[damage])  # Adversarial persisted input, never an authority seed.
    before = log.read_bytes()
    with pytest.raises(preparation._PreparationAuthorityRefused) as caught:
        preparation._issue_new_objective(healthy.root, 'f' * 32)
    assert caught.value.decision['nextAction'] == 'preparation_continuity_required'
    assert log.read_bytes() == before
    reserve_intent(healthy)


@pytest.mark.parametrize('kind', ['bytes', 'record_bytes', 'issued_ids'])
def test_birth_caps_preserve_tombstones_and_existing_authority(authority_factory, kind):
    healthy = authority_factory()
    log = healthy.root / '.preparation-authority-births-v1.jsonl'
    if kind == 'bytes':
        with log.open('ab') as stream:
            stream.write(b'x' * preparation.MAX_BIRTH_LOG_BYTES)
    elif kind == 'record_bytes':
        with log.open('ab') as stream:
            stream.write(b'x' * preparation.MAX_BIRTH_RECORD_BYTES + b'\n')
    else:
        # Keep the genuine header/first issuance and fill valid unique tombstones.
        with log.open('ab') as stream:
            for number in range(100, 100 + preparation.MAX_ISSUED_OBJECTIVES - 1):
                stream.write(preparation._birth_record({'kind': 'objective-issued', 'runId': f'{number:032x}', 'birthSessionId': '3' * 32}))
    before = log.read_bytes()
    with pytest.raises(preparation._PreparationAuthorityRefused) as caught:
        preparation._issue_new_objective(healthy.root, 'f' * 32)
    body, status = preparation.authority_refusal(caught.value)
    assert status == 409 and body['limitKind'] == kind
    assert body['limit'] == {'bytes': 4_194_304, 'record_bytes': 512, 'issued_ids': 10_000}[kind]
    assert body['retryable'] is False and body['noEffect'] is True
    assert body['wakeCondition'] == 'qualified_birth_log_capacity_revision'
    assert body['nextAction'] == 'preparation_issuance_limit_reached'
    assert log.read_bytes() == before and not preparation._NAMESPACE_FAULTS
    reserve_intent(healthy)


def test_append_ending_at_id_ceiling_succeeds_then_crossing_refuses(authority_factory):
    healthy = authority_factory()
    log = healthy.root / '.preparation-authority-births-v1.jsonl'
    with log.open('ab') as stream:
        for number in range(100, 100 + preparation.MAX_ISSUED_OBJECTIVES - 2):
            stream.write(preparation._birth_record({'kind': 'objective-issued', 'runId': f'{number:032x}', 'birthSessionId': '3' * 32}))
    preparation._issue_new_objective(healthy.root, 'e' * 32)
    before = log.read_bytes()
    assert len(before.splitlines()) == preparation.MAX_ISSUED_OBJECTIVES + 1
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation._issue_new_objective(healthy.root, 'f' * 32)
    assert log.read_bytes() == before


@pytest.mark.parametrize('boundary', ['file-fsync', 'replace', 'directory-fsync'])
def test_failed_row_commit_poison_survives_restored_io(authority_factory, monkeypatch, boundary):
    authority = authority_factory()
    before, revision = raw(authority), authority.revision
    calls = []
    original_atomic = preparation._atomic_json
    def counted(*args):
        calls.append(args[0])
        return original_atomic(*args)
    monkeypatch.setattr(preparation, '_atomic_json', counted)
    with monkeypatch.context() as patch:
        def fail(*_args, **_kwargs):
            raise OSError('injected ' + boundary)
        if boundary == 'file-fsync':
            patch.setattr(preparation.os, 'fsync', fail)
        elif boundary == 'replace':
            patch.setattr(Path, 'replace', fail)
        else:
            patch.setattr(preparation, '_sync_directory', fail)
        with pytest.raises(preparation._PreparationAuthorityRefused) as caught:
            reserve_intent(authority)
    assert caught.value.decision['nextAction'] == 'preparation_persistence_failed'
    assert authority.state == 'continuity_required' and authority.revision == revision
    assert authority.uncertain['objectiveBudget']['consumed'] == 1
    assert not preparation._HEALTHY[(str(authority.root), authority.run_id)].valid
    after = raw(authority)
    assert (after != before) is (boundary == 'directory-fsync')
    assert json.loads(after)['objectiveBudget']['consumed'] == (1 if boundary == 'directory-fsync' else 0)
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation._write(authority.row, authority=authority)
    assert len(calls) == 1 and raw(authority) == after
    retire(authority)
    assert not authority.lease.closed and authority.run_id not in preparation._ACTIVE
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation._acquire_authority(authority.root, authority.db, authority.run_id)
    independent = authority_factory({'id': 'f' * 32})
    reserve_intent(independent)


@pytest.mark.parametrize('loss', ['no-witness', 'new-session', 'missing-row', 'changed-ledger', 'changed-revision'])
def test_established_rows_never_regain_authority_from_json(authority_factory, monkeypatch, loss):
    authority = authority_factory()
    reserve_intent(authority)
    retire(authority)
    path = authority.directory / (authority.run_id + '.json')
    if loss == 'no-witness':
        preparation._HEALTHY.clear()
    elif loss == 'new-session':
        monkeypatch.setattr(preparation, '_SESSION', object())
    elif loss == 'missing-row':
        path.unlink()
    else:
        observed = json.loads(path.read_bytes())
        if loss == 'changed-ledger':
            del observed['providerBudget']
        else:
            observed['authority']['rowRevision'] += 1
        path.write_text(json.dumps(observed))
    before = path.read_bytes() if path.exists() else None
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation._acquire_authority(authority.root, authority.db, authority.run_id)
    assert (path.read_bytes() if path.exists() else None) == before
    assert authority.run_id not in preparation._LEASES


@pytest.mark.parametrize('ledger_shape', ['none', 'both', 'one'])
def test_legacy_namespace_is_observation_only(authority_factory, tmp_path, ledger_shape):
    directory = tmp_path / 'preparations'
    directory.mkdir()
    row = {'id': 'a' * 32, 'status': 'queued', 'actions': {'old': {'attempts': 3}}}
    if ledger_shape != 'none':
        admission_budget.initialize(row, 2)
    if ledger_shape == 'both':
        mcp_budget.initialize(row, 5)
    path = directory / (row['id'] + '.json')
    path.write_text(json.dumps(row))
    before = path.read_bytes()
    assert preparation.list_runs()[0]['id'] == row['id']
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation._issue_new_objective(tmp_path, 'b' * 32)
    assert path.read_bytes() == before
    assert not (tmp_path / '.preparation-authority-births-v1.jsonl').exists()
    assert not preparation._LEASES and not preparation._ACTIVE


def test_stale_callback_cannot_write_handoff_cancel_retire_or_release_successor(authority_factory):
    old = authority_factory()
    dispatch = reserve_intent(old)
    successor = resume(old)
    before, starts, cancellations = raw(successor), [], []
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation._write(old.row, authority=old)
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation._handoff(old, dispatch, lambda: starts.append('bad'))
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation._cancel_child(old, dispatch, 'child', cancellations.append)
    retire(old)
    preparation.list_runs()
    assert preparation._ACTIVE[old.run_id] is successor.slot
    assert preparation._LEASES[old.run_id] is successor.lease and not successor.lease.closed
    assert raw(successor) == before and starts == cancellations == []
    with preparation._guard(successor):
        preparation._write(successor.row, authority=successor)


def test_detached_stale_snapshot_cannot_erase_sibling_reservation(authority_factory):
    authority = authority_factory()
    detached = preparation._snapshot(authority)
    reserve_intent(authority)
    before = raw(authority)
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation._write(detached, authority=authority)
    assert raw(authority) == before
    assert json.loads(before)['objectiveBudget']['consumed'] == 1


def test_workflow_callback_is_detached_and_fenced_by_program_basis(authority_factory):
    authority = authority_factory({'checkpoints': {'Demo': {'programFingerprint': 'one'}}})
    mutate = preparation._workflow_mutator(authority)
    basis = {'program': 'Demo', 'fingerprint': 'one'}
    observed = mutate(basis, {'name': 'knowledge', 'values': {'knowledgeCursor': 3}})
    observed['knowledgeCursor'] = 999
    assert authority.row['checkpoints']['Demo']['knowledgeCursor'] == 3
    before = raw(authority)
    with pytest.raises(preparation._PreparationAuthorityRefused):
        mutate({**basis, 'fingerprint': 'old'}, {'name': 'knowledge', 'values': {'knowledgeCursor': 4}})
    assert raw(authority) == before


def test_late_workflow_and_comparison_callbacks_cannot_publish(authority_factory):
    old = authority_factory({'checkpoints': {'Demo': {'programFingerprint': 'one'}}, 'comparisonInputs': {'a': 1, 'b': 2}})
    mutate = preparation._workflow_mutator(old)
    successor = resume(old)
    before = raw(successor)
    with pytest.raises(preparation._PreparationAuthorityRefused):
        mutate({'program': 'Demo', 'fingerprint': 'one'}, {'name': 'knowledge', 'values': {'knowledgeCursor': 1}})
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation.record_comparison_receipt(old.run_id, 'a', 'b', {'ok': True, 'jobId': 'child'}, {'a': 1, 'b': 2}, authority=old)
    assert raw(successor) == before and 'comparisonReceipts' not in successor.row


def test_frozen_workspace_receipt_and_reference_commit_boundary(authority_factory, tmp_path, monkeypatch):
    inputs = {'a': {'digest': 'one'}, 'b': {'digest': 'two'}}
    authority = authority_factory({'comparisonInputs': inputs})
    other = tmp_path / 'other-root'
    other.mkdir()
    monkeypatch.setattr(preparation, 'live_root', lambda: other)
    monkeypatch.setattr(preparation, 'live_db', lambda: other / 'different.sqlite')
    preparation.record_comparison_receipt(authority.run_id, 'a', 'b', {'ok': True, 'jobId': 'child'}, inputs, authority=authority)
    receipt = preparation.read_comparison_receipt(authority.run_id, 'a', 'b', inputs, authority=authority)
    assert receipt['jobId'] == 'child' and receipt['db'] == str(authority.db)
    assert not (other / 'preparations').exists()
    before = raw(authority)
    original = preparation._atomic_json
    def fail_reference(path, value, suffix):
        if path == authority.directory / (authority.run_id + '.json'):
            raise OSError('reference commit failed after artifact')
        return original(path, value, suffix)
    monkeypatch.setattr(preparation, '_atomic_json', fail_reference)
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation.record_comparison_receipt(authority.run_id, 'a', 'b', {'ok': True, 'jobId': 'orphan'}, inputs, authority=authority)
    assert raw(authority) == before
    reference = next(iter(json.loads(before)['comparisonReceipts'].values()))
    assert json.loads(Path(reference['path']).read_bytes())['jobId'] == 'child'
    artifacts = list(authority.directory.rglob('*.json'))
    assert any(json.loads(path.read_bytes()).get('jobId') == 'orphan' for path in artifacts)
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation.read_comparison_receipt(authority.run_id, 'a', 'b', inputs, authority=authority)


def test_current_handoff_sees_durable_intent_and_pause_prevents_next_start(authority_factory):
    authority = authority_factory()
    dispatch = reserve_intent(authority)
    starts = []
    def start():
        assert json.loads(raw(authority))['objectiveBudget']['reservations'][dispatch]['status'] == 'intent'
        assert not preparation._LOCK._is_owned()
        starts.append('child')
        return 'child'
    assert preparation._handoff(authority, dispatch, start) == 'child'
    with preparation._guard(authority):
        admission_budget.acknowledge(authority.row, dispatch, 'child')
        admission_budget.acknowledge(authority.row, dispatch, 'child')
        preparation._write(authority.row, authority=authority)
    second = reserve_intent(authority, 'second')
    result = preparation.control({'preparation_id': authority.run_id, 'operation': 'pause'})
    assert result['controlAcknowledged']
    with pytest.raises(preparation._PauseRequested):
        preparation._handoff(authority, second, start)
    assert starts == ['child'] and authority.row['objectiveBudget']['consumed'] == 2


def test_uncertain_child_start_is_spent_and_never_retried(authority_factory):
    authority = authority_factory()
    dispatch = reserve_intent(authority)
    before, starts = raw(authority), []
    def ambiguous():
        starts.append('accepted-child')
        raise OSError('response lost after admission')
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation._handoff(authority, dispatch, ambiguous)
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation._handoff(authority, dispatch, ambiguous)
    assert starts == ['accepted-child'] and raw(authority) == before
    assert json.loads(before)['objectiveBudget']['reservations'][dispatch]['status'] == 'intent'


def test_control_merges_commands_and_failed_sync_never_acknowledges(authority_factory, monkeypatch):
    authority = authority_factory()
    params = {'preparation_id': authority.run_id}
    preparation.control({**params, 'operation': 'priority', 'priority': 75})
    result = preparation.control({**params, 'operation': 'budget', 'seconds': 600})
    assert result['control']['commandRevision'] == 2 and result['control']['priority'] == 75
    assert result['control']['budgetSeconds'] == 600
    with monkeypatch.context() as patch:
        def fail(*_):
            raise OSError('command fsync failed')
        patch.setattr(preparation, '_atomic_json', fail)
        with pytest.raises(preparation._PreparationAuthorityRefused) as caught:
            preparation.control({**params, 'operation': 'pause'})
    assert caught.value.decision['phase'] == 'control'
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation._handoff(authority, reserve_intent(authority), lambda: pytest.fail('must not dispatch'))
    assert json.loads(preparation._control_path(authority.run_id).read_bytes())['commandRevision'] == 2


def test_four_finished_faults_keep_leases_but_not_capacity(authority_factory, monkeypatch):
    faulted = []
    for number in range(4):
        authority = authority_factory({'id': f'{number + 32:032x}'})
        with monkeypatch.context() as patch:
            def fail(*_):
                raise OSError('failed commit')
            patch.setattr(preparation, '_atomic_json', fail)
            with pytest.raises(preparation._PreparationAuthorityRefused):
                reserve_intent(authority)
        assert preparation._ACTIVE[authority.run_id] is authority.slot
        retire(authority)
        faulted.append(authority)
    assert len(preparation._FAULTS) == 4 and not preparation._ACTIVE
    fifth = authority_factory({'id': 'f' * 32})
    reserve_intent(fifth)
    assert list(preparation._ACTIVE) == [fifth.run_id]
    assert all(not item.lease.closed and preparation._LEASES[item.run_id] is item.lease for item in faulted)


def test_admission_refusal_isolates_entry_and_busy_probe_has_cooldown(authority_factory, monkeypatch):
    healthy = authority_factory()
    root, fault, waiting = healthy.root, 'd' * 32, 'e' * 32
    calls = []
    now = [10.0]
    monkeypatch.setattr(preparation.time, 'monotonic', lambda: now[0])
    def submit(context, **_):
        calls.append(context['locator'])
        if context['locator'] == fault:
            raise preparation._refusal(fault)
        if context['locator'] == waiting:
            raise preparation._PreparationIssuanceWait(waiting)
    monkeypatch.setattr(preparation, 'submit', submit)
    preparation._admit_entry(root, fault, {'locator': fault})
    preparation._admit_entry(root, healthy.run_id, {'locator': healthy.run_id})
    now[0] += 1
    preparation._admit_entry(root, waiting, {'locator': waiting})
    preparation._admit_entry(root, waiting, {'locator': waiting})
    preparation._admit_entry(root, fault, {'locator': fault})
    assert calls == [fault, healthy.run_id, waiting]
    assert (str(root), fault) in preparation._SUSPENDED
    assert (str(root), waiting) not in preparation._SUSPENDED
    now[0] += 1
    preparation._admit_entry(root, waiting, {'locator': waiting})
    assert calls.count(waiting) == 2
    assert not preparation._FAULTS


@pytest.mark.parametrize('attempted', [False, True])
def test_root_start_failure_tracks_definite_vs_ambiguous_entry(authority_factory, monkeypatch, attempted):
    from agentdecompile_recovery.corpus.dashboard.actions import jobs
    root = preparation.live_root()
    run_id, starts = 'a' * 32, []
    monkeypatch.setattr(preparation, '_context_id', lambda _, **_kwargs: run_id)
    monkeypatch.setattr(preparation, '_project_context', lambda value: value)
    def start(_spec, _params, _argv, *, preparation_authority):
        authority = preparation_authority
        starts.append(authority)
        assert authority.committed['rootHandoff']['status'] == 'intent'
        authority.root_start('allocated', 'root-job')
        if attempted:
            authority.root_start('attempted', 'root-job')
        raise OSError('start return lost')
    monkeypatch.setattr(jobs, 'STORE', SimpleNamespace(start=start))
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation.submit({'locator': 'fixture'})
    authority = starts[0]
    before = raw(authority)
    assert authority.slot.job_id == 'root-job'
    assert (run_id in preparation._ACTIVE) is attempted
    assert not authority.lease.closed and preparation._FAULTS[(str(root), run_id)] is authority
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation.submit({'locator': 'fixture'}, resume=True)
    assert len(starts) == 1 and raw(authority) == before
    assert authority.row['objectiveBudget']['consumed'] == authority.row['providerBudget']['consumed'] == 0
    if attempted:
        authority.root_start('entered', 'root-job')
        authority.root_start('finished', 'root-job')
        assert run_id not in preparation._ACTIVE and not authority.lease.closed


@pytest.mark.parametrize('kind', ['lost', 'persistence', 'wait', 'control-wait', 'limit'])
def test_exact_catalog_direct_open_and_control_refusal_domains(authority_factory, monkeypatch, kind):
    from agentdecompile_recovery.corpus.dashboard import react_api, workbench
    from agentdecompile_recovery.corpus.dashboard.actions import jobs, job_history
    from agentdecompile_recovery.corpus.dashboard.actions.catalog import ActionSpec
    run_id = 'b' * 32
    errors = {'lost': preparation._refusal(run_id, 'preparation_authority_lost'),
              'persistence': preparation._refusal(run_id, 'preparation_persistence_failed'),
              'wait': preparation._PreparationIssuanceWait(run_id),
              'control-wait': preparation._PreparationControlWait(run_id, preparation.live_root()), 'limit': preparation._limit(run_id, 'issued_ids')}
    error = errors[kind]
    error.decision.update(secret='must not leak', row={'providerBudget': 'private'}, reason=error.decision['reason'])
    expected, status = preparation.authority_refusal(error)
    assert not {'secret', 'row'} & expected.keys()
    def refuse(*_args, **_kwargs):
        raise error
    monkeypatch.setattr(preparation, 'submit', refuse)
    monkeypatch.setattr(preparation, 'control', refuse)
    monkeypatch.setattr(preparation, 'execute', refuse)
    monkeypatch.setattr(jobs, '_active_duplicate', lambda *_: None)
    monkeypatch.setattr(jobs, '_external_pipeline_owner', lambda *_: None)
    spec = ActionSpec(id='workbench.prepare', title='Prepare', group='workbench', backend='preparation', command='prepare')
    monkeypatch.setattr(jobs, 'action_by_id', lambda _: spec)
    assert jobs.start_job(spec.id, {}) == (expected, status)
    router = react_api.create_react_router()
    endpoint = next(route.endpoint for route in router.routes if route.path.endswith('/workbench/prepare'))
    class Request:
        async def json(self):
            return {'locator': 'fixture', 'preparation_authority': {'forged': True}}
    response = asyncio.run(endpoint(Request()))
    assert response.status_code == status and json.loads(response.body) == expected
    monkeypatch.setattr(workbench, '_register_path_binary', lambda *_a, **_k: {'ok': True, 'binary': {'slug': 'fixture'}})
    opened = workbench.register_path_binary('fixture')
    assert opened['ok'] and opened['preparation'] == {**expected, 'httpStatus': status}
    # Real JobStore backend routing with inert thread starts and temporary history.
    monkeypatch.setattr(jobs, 'live_root', preparation.live_root)
    monkeypatch.setattr(job_history, 'directory', lambda: preparation.live_root() / 'jobs')
    monkeypatch.setattr(threading.Thread, 'start', lambda _: None)
    for backend in ('workflow-control', 'preparation'):
        spec = ActionSpec(id='workbench.workflow-control' if backend == 'workflow-control' else 'workbench.prepare',
                          title='Control' if backend == 'workflow-control' else 'Prepare',
                          group='workbench', backend=backend, command='control' if backend == 'workflow-control' else 'prepare')
        monkeypatch.setattr(jobs, 'action_by_id', lambda _: spec)
        store = jobs.JobStore()
        try:
            private = authority_factory({'id': run_id}) if backend == 'preparation' else None
            job = store.start(spec, {}, [], preparation_authority=private)
            assert job.preparation_authority is None and 'preparation_authority' not in job.to_dict()
            assert store._jobs[job.id].preparation_authority is private
            store._run(job.id, threading.Event())
            result = store.get(job.id)
            assert result.status == 'failed' and result.returncode == 1
            assert json.loads(result.log) == expected
            if private is not None:
                assert run_id not in preparation._ACTIVE
        finally:
            store._resource_owner_handle.close()


def test_command_contention_is_no_effect_then_same_witness_and_fresh_birth_progress(authority_factory):
    authority = authority_factory()
    params = {'preparation_id': authority.run_id, 'operation': 'priority', 'priority': 20}
    preparation.control(params)
    dispatch = reserve_intent(authority)
    command_path = preparation._control_path(authority.run_id, root=authority.root)
    row_before, command_before = raw(authority), command_path.read_bytes()
    witness = preparation._HEALTHY[(str(authority.root), authority.run_id)]
    starts = []
    with command_path.with_suffix('.lock').open('a+') as held:
        preparation._lock_lease(held)
        for operation in (
            lambda: preparation.control({**params, 'priority': 30}),
            lambda: preparation._handoff(authority, dispatch, lambda: starts.append('child')),
        ):
            with pytest.raises(preparation._PreparationControlWait) as caught:
                operation()
            body, status = preparation.authority_refusal(caught.value)
            assert status == 409 and body['status'] == 'waiting'
            assert body['nextAction'] == 'preparation_control_busy'
            assert body['wakeCondition'] == 'control_command_lock_available'
            assert body['phase'] == 'control' and body['retryAfterSeconds'] == 1
            assert body['retryable'] and body['noEffect'] and not body['durable']
        assert raw(authority) == row_before and command_path.read_bytes() == command_before
        assert witness.valid and authority.state == 'current'
        assert not preparation._COMMAND_FAULTS and not preparation._FAULTS and not preparation._SUSPENDED
        assert starts == [] and preparation._ACTIVE[authority.run_id] is authority.slot
    assert preparation.control({**params, 'priority': 30})['control']['commandRevision'] == 2
    preparation._handoff(authority, dispatch, lambda: starts.append('child'))
    assert starts == ['child']
    fresh = authority_factory({'id': 'f' * 32})
    reserve_intent(fresh)


@pytest.mark.parametrize('failure', ['permission', 'post-write'])
def test_command_noncontention_failure_stays_latched_after_io_recovers(authority_factory, monkeypatch, failure):
    authority = authority_factory()
    params = {'preparation_id': authority.run_id, 'operation': 'priority', 'priority': 20}
    preparation.control(params)
    path = preparation._control_path(authority.run_id)
    before, writes = path.read_bytes(), []
    original_atomic = preparation._atomic_json
    with monkeypatch.context() as patch:
        if failure == 'permission':
            def denied(_lease):
                raise PermissionError('command lease denied')
            patch.setattr(preparation, '_lock_lease', denied)
        else:
            def uncertain(target, value, suffix):
                writes.append(target)
                original_atomic(target, value, suffix)
                raise BlockingIOError('command durable acknowledgement uncertain')
            patch.setattr(preparation, '_atomic_json', uncertain)
        with pytest.raises(preparation._PreparationAuthorityRefused) as caught:
            preparation.control({**params, 'priority': 40})
    assert preparation.authority_refusal(caught.value)[1] == 503
    after = path.read_bytes()
    assert (after == before) is (failure == 'permission')
    assert len(writes) == (1 if failure == 'post-write' else 0)
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation.control({**params, 'priority': 50})
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation._read_control(authority.run_id, root=authority.root, strict=True)
    assert path.read_bytes() == after
    independent = authority_factory({'id': 'f' * 32})
    assert preparation.control({'preparation_id': independent.run_id, 'operation': 'priority', 'priority': 50})['controlAcknowledged']


@pytest.mark.parametrize('shape', ['list', 'null', 'priority', 'createdAt', 'updatedAt', 'deadline'])
@pytest.mark.parametrize('entrypoint', ['queue', 'inventory', 'recovery'])
def test_malformed_first_row_never_prevents_later_healthy_admission(authority_factory, monkeypatch, shape, entrypoint):
    bad = authority_factory({'id': 'a' * 32, 'status': 'queued', 'locator': 'bad-project'})
    good = authority_factory({'id': 'b' * 32, 'status': 'queued', 'locator': 'good-project'})
    retire(bad)
    retire(good)
    path = bad.directory / (bad.run_id + '.json')
    damaged = {'list': [], 'null': None}.get(shape, copy.deepcopy(bad.committed))
    if shape == 'priority':
        damaged['queuePriority'] = {'invalid': True}
    elif shape not in {'list', 'null'}:
        damaged[shape] = {'invalid': True}
    path.write_text(json.dumps(damaged))
    before, good_before, calls = path.read_bytes(), raw(good), []
    original_glob = Path.glob
    monkeypatch.setattr(Path, 'glob', lambda directory, pattern: iter(sorted(original_glob(directory, pattern))))
    monkeypatch.setattr(preparation, 'submit', lambda context, **_: calls.append(context['locator']) or {'ok': True})
    if entrypoint == 'queue':
        class OrderedWaiting(set):
            def __iter__(self):
                return iter(sorted(set.copy(self)))
        class OnePassWake:
            calls = 0
            def wait(self, _seconds):
                self.calls += 1
                if self.calls > 1:
                    raise StopIteration('one authored admission iteration completed')
            def clear(self):
                pass
        monkeypatch.setattr(preparation, '_WAITING', OrderedWaiting([bad.run_id, good.run_id]))
        monkeypatch.setattr(preparation, '_ADMISSION_WAKE', OnePassWake())
        monkeypatch.setattr(preparation, '_collect_inventory_admissions', lambda: None)
        with pytest.raises(StopIteration, match='one authored admission iteration'):
            preparation._drain_admissions()
    elif entrypoint == 'inventory':
        directory = preparation._inventory_directory()
        directory.mkdir()
        for item in (bad, good):
            (directory / (item.run_id + '.json')).write_text(json.dumps({'id': item.run_id, 'locator': item.row['locator'], 'generation': 'new'}))
        preparation._collect_inventory_admissions()
    else:
        preparation.recover_interrupted()
    assert calls == [good.row['locator']]
    assert path.read_bytes() == before and raw(good) == good_before
    assert preparation._HEALTHY[(str(good.root), good.run_id)].valid


@pytest.mark.parametrize('loss', ['closed-lease', 'replaced-lease', 'session', 'slot', 'run-id'])
def test_execute_prebody_loss_poison_cannot_be_healed_by_root_finalizer(authority_factory, monkeypatch, loss):
    authority = authority_factory()
    authority.root_start('allocated', 'root')
    before, witness = raw(authority), preparation._HEALTHY[(str(authority.root), authority.run_id)]
    run_id = authority.run_id
    if loss == 'closed-lease':
        authority.lease.close()
    elif loss == 'replaced-lease':
        # Registry identity loss; substitute is a real fixture-owned descriptor.
        replacement = (authority.root / 'replacement.lock').open('a+')
        preparation._lock_lease(replacement)
        preparation._LEASES[run_id] = replacement
    elif loss == 'session':
        monkeypatch.setattr(preparation, '_SESSION', object())
    elif loss == 'slot':
        preparation._retire_capacity(authority.slot)
    else:
        run_id = 'f' * 32
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation.execute({'preparation_id': run_id}, threading.Event(), authority=authority)
    assert not witness.valid and authority.state == 'continuity_required'
    authority.root_start('finished', 'root')
    assert authority.run_id not in preparation._ACTIVE and raw(authority) == before
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation._acquire_authority(authority.root, authority.db, authority.run_id)
    assert raw(authority) == before


@pytest.mark.parametrize('boundary', ['healthy', 'action', 'checkpoint'])
def test_extractor_original_persistence_refusal_survives_finally_without_second_mutation(authority_factory, monkeypatch, boundary):
    from agentdecompile_recovery.corpus.dashboard import workflow
    authority = authority_factory({'checkpoints': {'Demo': {'programFingerprint': 'one'}}})
    checkpoint = copy.deepcopy(authority.row['checkpoints']['Demo'])
    mutations, failures, snapshots = [], [], []
    real_mutate = preparation._workflow_mutator(authority)
    real_atomic = preparation._atomic_json
    def mutate(basis, operation):
        mutations.append(copy.deepcopy(operation))
        return real_mutate(basis, operation)
    def fail(target, value, suffix):
        failures.append(target)
        raise OSError('original extractor persistence failure')
    def action(*_args):
        snapshots.append(raw(authority))
        if boundary != 'healthy':
            monkeypatch.setattr(preparation, '_atomic_json', fail)
        if boundary == 'action':
            reserve_intent(authority)
        return {'ok': True, 'data': {'more': False, 'cursor': 'done', 'available': 1, 'attempted': 1, 'total': 1}}
    monkeypatch.setattr(workflow, '_knowledge_has_program', lambda *_: True)
    kwargs = dict(row=preparation._snapshot(authority), checkpoint=checkpoint, work=authority.root,
                  program='Demo', context={'program': 'Demo'}, action=action,
                  update=lambda *_a, **_k: None, mutate_state=mutate)
    if boundary == 'healthy':
        assert workflow._extract_advisory_witnesses(**kwargs)[1]
        assert mutations[-1]['name'] == 'progress-file' and mutations[-1]['clear']
        assert 'functionProgressFile' not in authority.row and not failures
    else:
        with pytest.raises(preparation._PreparationAuthorityRefused) as caught:
            workflow._extract_advisory_witnesses(**kwargs)
        body, status = preparation.authority_refusal(caught.value)
        assert status == 503 and body['nextAction'] == 'preparation_persistence_failed'
        assert len(failures) == 1 and not any(item.get('clear') for item in mutations)
        assert raw(authority) == snapshots[0]
        assert authority.state == 'continuity_required'
        monkeypatch.setattr(preparation, '_atomic_json', real_atomic)
        independent = authority_factory({'id': 'f' * 32})
        reserve_intent(independent)


def test_second_issuer_rechecks_fault_latch_after_precheck_before_acquisition(authority_factory, monkeypatch):
    healthy = authority_factory()
    root, first_id, second_id = healthy.root, 'a' * 32, 'b' * 32
    log = root / '.preparation-authority-births-v1.jsonl'
    original_lock = preparation._lock_lease
    interleaving, first_error = [], []
    def interleaved_lock(handle):
        if not interleaving:
            interleaving.append('B passed precheck; A acquires first')
            with monkeypatch.context() as patch:
                def fail_sync(_path):
                    raise OSError('A appended valid bytes but directory fsync failed')
                patch.setattr(preparation, '_sync_directory', fail_sync)
                with pytest.raises(preparation._PreparationAuthorityRefused) as caught:
                    preparation._issue_new_objective(root, first_id)
                first_error.append(caught.value)
            interleaving.append('A fault latched and lock released; B acquires')
        original_lock(handle)
    monkeypatch.setattr(preparation, '_lock_lease', interleaved_lock)
    with pytest.raises(preparation._PreparationAuthorityRefused) as caught:
        preparation._issue_new_objective(root, second_id)
    assert caught.value is first_error[0]
    records = [json.loads(line) for line in log.read_bytes().splitlines()]
    assert [record['runId'] for record in records[1:]] == [healthy.run_id, first_id]
    assert (str(root), first_id) not in preparation._BIRTHS and (str(root), second_id) not in preparation._BIRTHS
    assert second_id not in preparation._ACTIVE and second_id not in preparation._LEASES
    assert not (root / 'preparations' / (second_id + '.json')).exists()
    before = log.read_bytes()
    with pytest.raises(preparation._PreparationAuthorityRefused):
        preparation._issue_new_objective(root, second_id)
    assert log.read_bytes() == before
    reserve_intent(healthy)


def test_jobstore_prebody_loss_retires_exact_root_and_ordinary_job_still_completes(authority_factory, monkeypatch):
    from agentdecompile_recovery.corpus.dashboard.actions import jobs, job_history
    from agentdecompile_recovery.corpus.dashboard.actions.catalog import ActionSpec
    authority = authority_factory()
    monkeypatch.setattr(jobs, 'live_root', preparation.live_root)
    monkeypatch.setattr(job_history, 'directory', lambda: authority.root / 'jobs')
    monkeypatch.setattr(threading.Thread, 'start', lambda _: None)
    root = ActionSpec(id='workbench.prepare', title='Prepare', group='workbench', backend='preparation', command='prepare')
    ordinary = ActionSpec(id='fixture.read', title='Read', group='fixture', backend='cli', command='read')
    monkeypatch.setattr(jobs, 'action_by_id', lambda name: root if name == root.id else ordinary)
    effects = []
    monkeypatch.setattr(jobs, '_default_executor', lambda *_a, **_k: (effects.append('ordinary') or 0, '{"ok":true}'))
    store = jobs.JobStore()
    try:
        job = store.start(root, {'preparation_id': authority.run_id}, [], preparation_authority=authority)
        slot, before = authority.slot, raw(authority)
        assert slot.job_id == job.id and slot.worker_start_attempted
        assert store._jobs[job.id].preparation_authority is authority
        assert job.preparation_authority is None and 'preparation_authority' not in job.to_dict()
        authority.lease.close()
        store._run(job.id, threading.Event())
        result = store.get(job.id)
        assert result.status == 'failed' and result.returncode == 1
        assert json.loads(result.log)['nextAction'] == 'preparation_authority_lost'
        assert slot.entered and slot.finished and authority.run_id not in preparation._ACTIVE
        assert raw(authority) == before and authority.state == 'continuity_required'
        assert not preparation._HEALTHY[(str(authority.root), authority.run_id)].valid
        with pytest.raises(preparation._PreparationAuthorityRefused):
            resume(authority)
        other = store.start(ordinary, {}, [])
        store._run(other.id, threading.Event())
        assert store.get(other.id).status == 'ok' and effects == ['ordinary']
        assert raw(authority) == before
    finally:
        store._resource_owner_handle.close()


def test_healthy_catalog_direct_open_and_control_keep_public_behavior(authority_factory, monkeypatch):
    from agentdecompile_recovery.corpus.dashboard import react_api, workbench
    from agentdecompile_recovery.corpus.dashboard.actions import jobs, job_history
    from agentdecompile_recovery.corpus.dashboard.actions.catalog import ActionSpec
    authority = authority_factory()
    accepted = {'id': authority.run_id, 'status': 'queued', 'jobId': 'root'}
    seen = []
    def submit(context, **kwargs):
        seen.append((context, kwargs))
        return copy.deepcopy(accepted)
    monkeypatch.setattr(preparation, 'submit', submit)
    monkeypatch.setattr(jobs, '_active_duplicate', lambda *_: None)
    monkeypatch.setattr(jobs, '_external_pipeline_owner', lambda *_: None)
    monkeypatch.setattr(jobs, 'get_job', lambda _: None)
    spec = ActionSpec(id='workbench.prepare', title='Prepare', group='workbench', backend='preparation', command='prepare')
    monkeypatch.setattr(jobs, 'action_by_id', lambda _: spec)
    body, status = jobs.start_job(spec.id, {})
    assert status == 202 and body['ok'] and body['run'] == accepted
    endpoint = next(route.endpoint for route in react_api.create_react_router().routes if route.path.endswith('/workbench/prepare'))
    class Request:
        async def json(self):
            return {'locator': 'fixture', 'preparation_authority': {'forged': True}, 'providerBudget': {'consumed': 0}}
    response = asyncio.run(endpoint(Request()))
    assert response.status_code == 202 and json.loads(response.body) == {'ok': True, 'run': accepted}
    assert seen[-1][0] == {'locator': 'fixture', 'program': '', 'slug': ''}
    monkeypatch.setattr(workbench, '_register_path_binary', lambda *_a, **_k: {'ok': True, 'binary': {'slug': 'fixture'}})
    opened = workbench.register_path_binary('fixture')
    assert opened['ok'] and opened['preparation']['status'] == 'queued'
    assert 'httpStatus' not in opened['preparation']
    monkeypatch.setattr(jobs, 'live_root', preparation.live_root)
    monkeypatch.setattr(job_history, 'directory', lambda: authority.root / 'jobs')
    monkeypatch.setattr(threading.Thread, 'start', lambda _: None)
    control = ActionSpec(id='workbench.workflow-control', title='Control', group='workbench', backend='workflow-control', command='control')
    monkeypatch.setattr(jobs, 'action_by_id', lambda _: control)
    store = jobs.JobStore()
    try:
        job = store.start(control, {'preparation_id': authority.run_id, 'operation': 'priority', 'priority': 70}, [])
        store._run(job.id, threading.Event())
        result = store.get(job.id)
        assert result.status == 'ok' and result.returncode == 0
        assert json.loads(result.log)['controlAcknowledged']
        assert preparation._read_control(authority.run_id)['priority'] == 70
    finally:
        store._resource_owner_handle.close()


@pytest.mark.parametrize('switch_workspace', [False, True])
def test_execution_route_discovery_uses_captured_database_and_root(authority_factory, monkeypatch, switch_workspace):
    from agentdecompile_recovery.corpus import ghidra_project
    authority = authority_factory()
    other_root = authority.root / 'workspace-b'
    other_root.mkdir()
    project_a = authority.root / 'workspace' / 'a.gpr'
    project_b = other_root / 'workspace' / 'b.gpr'
    for path in (project_a, project_b):
        path.parent.mkdir()
        path.write_text('inert discovery fixture')
    before_b = project_b.read_bytes()
    queries, discoveries = [], []
    def query(sql, *_, db=None):
        queries.append(db)
        return [], None
    def inspect(locator):
        discoveries.append(locator)
        return {'kind': 'ghidra-project', 'programs': ['Demo.exe']}
    monkeypatch.setattr(preparation, 'query_db', query)
    monkeypatch.setattr(ghidra_project, 'inspect_locator', inspect)
    monkeypatch.setattr(ghidra_project, 'shared_defaults', lambda: {})
    if switch_workspace:
        monkeypatch.setattr(preparation, 'live_root', lambda: other_root)
        monkeypatch.setattr(preparation, 'live_db', lambda: other_root / 'corpus.sqlite')
    routes = preparation._execution_program_bindings(str(authority.root / 'repository'), {'kind': 'shared-fs'}, ['Demo.exe'], root=authority.root, db=authority.db)
    assert routes == {'Demo.exe': (str(project_a.resolve()), 'Demo.exe')}
    assert queries == [authority.db] and discoveries == [str(project_a.resolve())]
    assert project_b.read_bytes() == before_b and not (other_root / 'preparations').exists()


def test_nested_mcp_first_persistence_cause_survives_parent_guard_and_restored_io(authority_factory, monkeypatch):
    authority = authority_factory()
    reserve = preparation._mcp_reservation_capability(authority, dispatch_id='child', action_id='read')
    before, writes = raw(authority), []
    with monkeypatch.context() as patch:
        def fail(path, *_):
            writes.append(path)
            raise OSError('provider intent durability failed')
        patch.setattr(preparation, '_atomic_json', fail)
        with pytest.raises(mcp_budget.DispatchRefused) as child:
            reserve('read')
    cause = child.value.decision['preparationCause']
    assert cause['nextAction'] == 'preparation_persistence_failed' and cause['phase'] == 'intent'
    for _ in range(2):
        with pytest.raises(preparation._PreparationAuthorityRefused) as parent:
            with preparation._guard(authority):
                pytest.fail('faulted current parent must not regain the gate')
        body, status = preparation.authority_refusal(parent.value)
        assert status == 503 and body == cause
    assert len(writes) == 1 and raw(authority) == before
    assert authority.row['providerBudget']['consumed'] == 1
    healthy = authority_factory({'id': 'f' * 32})
    stale_reserve = preparation._mcp_reservation_capability(healthy)
    successor = resume(healthy)
    successor_before = raw(successor)
    with pytest.raises(mcp_budget.DispatchRefused) as stale:
        stale_reserve('read')
    assert stale.value.decision['nextAction'] == 'provider_authority_lost'
    assert stale.value.decision['preparationCause']['nextAction'] == 'preparation_authority_lost'
    assert successor.state == 'current' and raw(successor) == successor_before
    preparation._mcp_reservation_capability(successor)('read')
    assert successor.row['providerBudget']['consumed'] == 1


def test_child_defaults_slug_resolution_and_store_root_remain_captured_after_workspace_switch(authority_factory, tmp_path, monkeypatch):
    from agentdecompile_recovery.corpus.dashboard.actions import catalog, jobs, job_history
    from agentdecompile_recovery.corpus.dashboard.actions.catalog import ActionSpec, FieldSpec
    monkeypatch.setattr(catalog, 'KNOWLEDGE_DB', None)
    monkeypatch.delenv('AGENT_DECOMPILE_GHIDRA_KNOWLEDGE_DB', raising=False)
    (tmp_path / 'corpus_work').mkdir()
    authority = authority_factory()
    other_root = authority.root / 'workspace-b'
    (other_root / 'corpus_work').mkdir(parents=True)
    other_db = other_root / 'corpus.sqlite'
    sentinel = other_root / 'unrelated-control.json'
    sentinel.write_text('{"priority":42}')
    sentinel_before = sentinel.read_bytes()
    for module in (preparation, jobs):
        monkeypatch.setattr(module, 'live_root', lambda: other_root)
    monkeypatch.setattr(preparation, 'live_db', lambda: other_db)
    monkeypatch.setattr(catalog, 'live_db', lambda: other_db)
    monkeypatch.setattr(catalog, 'runtime_project_root', lambda: other_root)
    monkeypatch.setattr(catalog, 'runtime_work_dir', lambda: other_root / 'corpus_work')
    query_dbs = []
    def query(_sql, _params, *, db=None, **_):
        query_dbs.append(db)
        return [('/a/Demo.exe' if db == authority.db else '/b/Demo.exe',)], None
    monkeypatch.setattr(catalog, 'query_db', query)
    spec = ActionSpec(id='fixture.read', title='Read', group='fixture', backend='cli', command='read',
                      fields=tuple(FieldSpec(name, from_context=name) for name in ('db', 'work_dir', 'kb', 'report_file', 'program', 'repo', 'slug')))
    monkeypatch.setattr(jobs, 'action_by_id', lambda _: spec)
    monkeypatch.setattr(jobs, '_active_duplicate', lambda *_: None)
    monkeypatch.setattr(jobs, '_external_pipeline_owner', lambda *_: None)
    monkeypatch.setattr(jobs, 'build_command', lambda _spec, _params: ['inert-fixture'])
    monkeypatch.setattr(job_history, 'directory', lambda: authority.root / 'jobs')
    monkeypatch.setattr(threading.Thread, 'start', lambda _: None)
    store = jobs.JobStore()
    monkeypatch.setattr(jobs, 'STORE', store)
    try:
        before = raw(authority)
        response, status = jobs.start_job(spec.id, {}, context={'slug': 'demo'}, _execution_context=authority)
        assert status == 202
        child = store._jobs[response['job']['id']]
        assert child.execution_root == str(authority.root)
        assert child.params == {'db': str(authority.db), 'work_dir': str(authority.root / 'corpus_work'),
                                'kb': str(authority.root / 'ghidra_knowledge.sqlite'),
                                'report_file': str(authority.root / 'recovery-report.json'),
                                'program': '/a/Demo.exe', 'repo': '/a/Demo.exe', 'slug': 'demo'}
        assert child.preparation_authority is None
        assert '_execution_context' not in child.to_dict() and '_execution_context' not in child.params
        assert query_dbs == [authority.db]
        ordinary, status = jobs.start_job(spec.id, {}, context={'slug': 'demo'})
        assert status == 202
        ordinary_child = store._jobs[ordinary['job']['id']]
        assert ordinary_child.execution_root == str(other_root)
        assert ordinary_child.params['db'] == str(other_db)
        assert ordinary_child.params['work_dir'] == str(other_root / 'corpus_work')
        assert ordinary_child.params['kb'] == str(other_root / 'ghidra_knowledge.sqlite')
        assert ordinary_child.params['report_file'] == str(other_root / 'recovery-report.json')
        assert ordinary_child.params['program'] == '/b/Demo.exe'
        assert query_dbs == [authority.db, None]
        for params, context in (({'db': str(other_db)}, {}), ({}, {'db': str(other_db)})):
            with pytest.raises(ValueError, match='conflicts with its captured workspace'):
                jobs.start_job(spec.id, params, context=context, _execution_context=authority)
        assert len(store._jobs) == 2 and query_dbs == [authority.db, None]
        assert raw(authority) == before and sentinel.read_bytes() == sentinel_before
        assert not (other_root / 'preparations').exists()
    finally:
        store._resource_owner_handle.close()


@pytest.mark.parametrize('faulted', [False, True])
def test_jobstore_early_persistence_return_finalizes_captured_root_without_entering_execute(authority_factory, monkeypatch, faulted):
    from agentdecompile_recovery.corpus.dashboard.actions import jobs, job_history
    from agentdecompile_recovery.corpus.dashboard.actions.catalog import ActionSpec
    authority = authority_factory()
    monkeypatch.setattr(jobs, 'live_root', preparation.live_root)
    monkeypatch.setattr(job_history, 'directory', lambda: authority.root / 'jobs')
    monkeypatch.setattr(threading.Thread, 'start', lambda _: None)
    spec = ActionSpec(id='workbench.prepare', title='Prepare', group='workbench', backend='preparation', command='prepare')
    monkeypatch.setattr(jobs, 'action_by_id', lambda _: spec)
    monkeypatch.setattr(preparation, 'execute', lambda *_a, **_k: pytest.fail('early store persistence failure must not enter execute'))
    store = jobs.JobStore()
    try:
        job = store.start(spec, {'preparation_id': authority.run_id}, [], preparation_authority=authority)
        if faulted:
            with monkeypatch.context() as patch:
                patch.setattr(preparation, '_atomic_json', lambda *_: (_ for _ in ()).throw(OSError('row fault before worker entry')))
                with pytest.raises(preparation._PreparationAuthorityRefused):
                    reserve_intent(authority)
        before, persisted = raw(authority), []
        def fail_running(job, **_):
            persisted.append(job.status)
            raise OSError('store running-state durability failure')
        monkeypatch.setattr(store, '_persist_locked', fail_running)
        store._run(job.id, threading.Event())
        assert persisted == ['running'] and store.get(job.id).status == 'failed'
        assert authority.slot.entered and authority.slot.finished
        assert authority.run_id not in preparation._ACTIVE and raw(authority) == before
        assert authority.lease.closed is (not faulted)
        if faulted:
            assert preparation._FAULTS[(str(authority.root), authority.run_id)] is authority
            with pytest.raises(preparation._PreparationAuthorityRefused):
                resume(authority)
        else:
            successor = resume(authority)
            authority.root_start('finished', job.id)
            assert preparation._ACTIVE[authority.run_id] is successor.slot
            reserve_intent(successor)
    finally:
        store._resource_owner_handle.close()


@pytest.mark.parametrize('spelling', ['symlink', 'relative'])
def test_inventory_and_submit_keep_raw_selected_db_objective_identity(authority_factory, tmp_path, monkeypatch, spelling):
    import hashlib
    from agentdecompile_recovery.corpus.dashboard.actions import jobs
    physical = tmp_path / 'physical.sqlite'
    physical.write_bytes(b'inert path identity fixture; never opened as SQLite')
    if spelling == 'symlink':
        selected = tmp_path / 'selected.sqlite'
        selected.symlink_to(physical)
    else:
        monkeypatch.chdir(tmp_path)
        selected = Path('physical.sqlite')
    monkeypatch.setattr(preparation, 'live_db', lambda: selected)
    monkeypatch.setattr(preparation, '_project_context', lambda value: value)
    context = {'locator': 'fixture'}
    expected = hashlib.sha256(json.dumps([str(selected), 'fixture', '', '']).encode()).hexdigest()[:32]
    issued = preparation.inventory_changed('fixture')
    assert issued['id'] == expected
    request_path = tmp_path / 'preparation-inventory-v1' / (expected + '.json')
    request_before = request_path.read_bytes()
    captured = []
    def start(_spec, _params, _argv, *, preparation_authority):
        captured.append(preparation_authority)
        return SimpleNamespace(id='root-' + str(len(captured)))
    monkeypatch.setattr(jobs, 'STORE', SimpleNamespace(start=start))
    first = preparation.submit(context)
    assert first['id'] == expected and first['inventoryGeneration'] == issued['inventoryGeneration']
    authority = captured[0]
    assert authority.db == physical.resolve()
    successor = resume(authority)
    reserve_intent(successor)
    with preparation._guard(successor):
        successor.row['actions']['prior'] = {'attempts': 3, 'status': 'interrupted'}
        preparation._write(successor.row, authority=successor)
    histories = {key: copy.deepcopy(successor.row[key]) for key in ('objectiveBudget', 'providerBudget', 'actions')}
    retire(successor)
    second = preparation.submit(context, resume=True)
    assert second['id'] == expected and second['inventoryGeneration'] == issued['inventoryGeneration']
    assert {key: second[key] for key in histories} == histories
    assert captured[-1].db == physical.resolve()
    assert len((tmp_path / '.preparation-authority-births-v1.jsonl').read_bytes().splitlines()) == 2
    assert request_path.read_bytes() == request_before
